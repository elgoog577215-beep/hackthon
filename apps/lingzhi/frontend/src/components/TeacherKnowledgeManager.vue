<template>
  <section class="knowledge-workspace teacher-knowledge-manager" :class="{ 'tree-only': treeOnly }">
    <div v-if="!treeOnly" class="manager-tools"><span>{{ data?.title }}</span><button @click="refresh" :disabled="busy">{{ t('common.refresh') }}</button></div>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="observationNotice" class="notice observation-notice" role="status" data-testid="knowledge-observation-notice">
      {{ t(`knowledgeFirst.${observationNotice}`) }}
      <button type="button" :disabled="busy" @click="retryObservation">{{ t('knowledgeFirst.refreshStatus') }}</button>
    </p>
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
            <option v-if="treeChoice === 'candidate' && !selectedCandidate && data.tree" value="candidate" disabled>{{ t('knowledgeFirst.candidatePreparingBaseline') }}</option>
            <option v-if="selectedCandidate && selectedCandidate.revision_id !== data.knowledge_revision" value="candidate">{{ t('knowledgeFirst.candidate') }} · {{ short(selectedCandidate.revision_id) }}</option>
            <option v-for="v in historyOptions" :key="v.revision_id" :value="v.revision_id">{{ v.revision_id === data.knowledge_revision ? t('knowledgeFirst.current') : t('knowledgeFirst.history') }} · {{ short(v.revision_id) }}</option>
          </select></label>
          <button v-if="treeOnly && treeChoice === 'candidate' && displayTree && data.can_edit && canAdoptSelection" class="primary" :disabled="busy || activeJobs.length > 0 || staleTreeSource || displayTree.revision_id === data.knowledge_revision || displayTree.teaching_assessment?.ready_for_adoption === false || !atomicAdoptionReady" @click="adopt">{{ t('knowledgeFirst.adoptTree') }}</button>
          <div v-if="!treeOnly && (!derived || data.handouts?.length)" class="tabs"><button :class="{ active: tab === 'tree' }" @click="tab = 'tree'">{{ t('knowledgeFirst.tree') }}</button>
            <button :class="{ active: tab === 'handout' }" @click="tab = 'handout'">{{ t('knowledgeFirst.handouts') }}</button></div>
          <button v-if="data.can_edit" class="primary" :disabled="busy || blockingJobs.length > 0 || (perLesson ? !selectedLesson?.can_generate : derived ? !data.can_generate_tree : generic && (inputDirty || !data.inputs?.material_asset_ids?.length))" @click="generate('tree')">{{ t(perLesson ? 'knowledgeFirst.generateLessonTree' : derived ? (data.tree ? 'knowledgeFirst.updateFromHandouts' : 'knowledgeFirst.generateFromHandouts') : data.tree ? 'knowledgeFirst.regenerateTree' : 'knowledgeFirst.generateTree') }}</button>
          <button v-if="data.can_edit && perLesson" type="button" data-testid="generate-knowledge-relations" :disabled="busy || blockingJobs.length > 0 || !canGenerateRelations" :title="t('knowledgeFirst.relationRequiresBaseline')" @click="generateRelations()">{{ t('knowledgeFirst.generateRelations') }}</button>
        </div>
        <div v-if="perLesson" class="knowledge-lesson-switch">
          <button type="button" :disabled="lessonOptions[0]?.lesson_id === knowledgeLessonId" @click="stepLesson(-1)">{{ t('knowledgeFirst.previousLesson') }}</button>
          <select v-model="knowledgeLessonId" :aria-label="t('knowledgeFirst.lessonPicker')"><option v-for="l in lessonOptions" :key="l.lesson_id" :value="l.lesson_id">{{ lessonLabels[l.lesson_id] }}</option></select>
          <button type="button" :disabled="lessonOptions.at(-1)?.lesson_id === knowledgeLessonId" @click="stepLesson(1)">{{ t('knowledgeFirst.nextLesson') }}</button>
        </div>
        <p v-if="staleTreeSource" class="notice error source-version-warning" role="alert">
          {{ t(treeChoice === 'candidate' ? 'knowledgeFirst.candidateSourceChanged' : 'knowledgeFirst.adoptedSourceChanged') }}
        </p>
        <section v-for="job in sourceBlockingJobs" :key="job.id" class="notice job" role="status" data-testid="knowledge-source-blocker">
          <strong>{{ blockingJobLabel(job) }}</strong>
          <span>{{ job.progress || 0 }}% · {{ t('knowledgeFirst.waitForSourceTask') }}</span>
        </section>
        <section v-if="progressJob" class="notice job generation-progress" role="status" aria-live="polite" data-testid="knowledge-generation-progress">
          <div class="generation-progress-heading">
            <strong>{{ progressJob.knowledge_lesson_id ? `${lessonLabels[progressJob.knowledge_lesson_id] || ''} · ` : '' }}{{ progressJob.status === 'completed' ? t('knowledgeFirst.phase_completed') : jobPhase(progressJob) }}</strong>
            <strong class="generation-progress-percent">{{ progressPercent }}%</strong>
          </div>
          <div class="generation-progress-track" role="progressbar" :aria-valuenow="progressPercent" aria-valuemin="0" aria-valuemax="100" :aria-label="t('knowledgeFirst.generationProgress')">
            <span :style="{ width: `${progressPercent}%` }" />
          </div>
          <div class="generation-progress-actions">
            <button v-if="data.can_edit && activeJob" type="button" :disabled="busy" @click="mutate(`cancel/${activeJob.id}`)">{{ t('knowledgeFirst.cancel') }}</button>
            <button v-if="data.can_edit && atomicCanContinue" type="button" data-testid="continue-knowledge-batches" :disabled="busy || blockingJobs.length > 0" @click="continueAtomic(relationOnlyContinue ? 'relations' : '')">{{ t('knowledgeFirst.continueGeneration') }}</button>
            <button v-if="data.can_edit && atomicCanOrganize" type="button" data-testid="organize-knowledge-hierarchy" :disabled="busy || blockingJobs.length > 0" @click="continueAtomic('hierarchy')">{{ t('knowledgeFirst.organizeHierarchy') }}</button>
            <button v-if="data.can_edit && atomicCanRebuild" type="button" data-testid="rebuild-knowledge-leaves" :disabled="busy || blockingJobs.length > 0" @click="continueAtomic('all_atoms')">{{ t('knowledgeFirst.reviseCandidate') }}</button>
            <button v-if="data.can_edit && relationCanContinue" type="button" :disabled="busy || blockingJobs.length > 0" @click="generateRelations(true)">{{ t('knowledgeFirst.continueGeneration') }}</button>
          </div>
        </section>
        <p v-if="treeOnly && !activeJob && latestJob?.status === 'failed'" class="notice error" role="alert"><strong>{{ t('knowledgeFirst.lastGenerationFailed') }}：</strong>{{ generationFailureMessage(latestJob) }} <button v-if="data.can_edit && latestJob.recheck_available" :disabled="busy" @click="recheck(latestJob.id)">{{ t('knowledgeFirst.recheck') }}</button></p>
        <details v-if="!treeOnly && failedJobs.length" class="notice"><summary>{{ t('knowledgeFirst.jobHistory') }} · {{ failedJobs.length }}</summary>
          <details v-for="job in failedJobs" :key="job.id" class="notice error"><summary>{{ t('knowledgeFirst.interrupted') }} · {{ job.id }}</summary>
            <p>{{ generationFailureMessage(job) }}</p><button v-if="data.can_edit && job.recheck_available" :disabled="busy || !!activeJob" @click="recheck(job.id)">{{ t('knowledgeFirst.recheck') }}</button><pre v-if="job.partial_text">{{ job.partial_text }}</pre><p v-if="!['AIRequestBudgetExceeded', 'ModelConnectionUnavailable'].includes(job.error?.code)">{{ t('knowledgeFirst.retryHint') }}</p></details>
        </details>
        <details v-if="treeChoice === 'candidate' && displayTree?.relation_assessment" class="notice relation-adoption" data-testid="knowledge-relation-adoption">
          <summary>{{ t('knowledgeFirst.relationCandidateCount').replace('{count}',String(displayTree.relation_assessment.proposed_count)) }} · {{ t('knowledgeFirst.relationDetails') }}</summary>
          <p>{{ t('knowledgeFirst.relationSelectHint') }}</p>
          <div v-for="edge in proposedRelations" :key="edge.id" class="relation-option">
            <label><input v-model="selectedRelationIds" type="checkbox" :value="edge.id" :data-relation-id="edge.id" @change="confirmRelations = false" /> {{ pointName(edge.source_id) }} → {{ pointName(edge.target_id) }} · {{ t(`knowledgeFirst.relationTypes.${edge.type}`,edge.type) }}</label>
            <details class="relation-explanation" data-testid="knowledge-relation-reason"><summary>{{ t('knowledgeFirst.relationReason') }}</summary><p>{{ edge.reason }}</p></details>
          </div>
          <p v-for="(gap,index) in displayTree.relation_assessment.gaps || []" :key="index">{{ gap }}</p>
          <label><input v-model="confirmRelations" type="checkbox" data-testid="confirm-knowledge-relations" /> {{ t('knowledgeFirst.confirmRelations') }}</label>
        </details>
        <p v-if="displayTree?.generation_preview" class="notice" role="status">{{ t('knowledgeFirst.streamingPreview') }}</p>
        <section v-if="treeChoice === 'candidate' && displayTree?.atomic_assessment && !displayTree.generation_preview" class="notice atomic-adoption" data-testid="knowledge-atomic-adoption">
          <p v-if="displayTree.atomic_assessment.ready_for_adoption === false">{{ t('knowledgeFirst.candidateNeedsRevision') }}</p>
          <label v-if="atomicReviewRequired"><input v-model="confirmAtomicReview" type="checkbox" /> {{ t('knowledgeFirst.confirmAtomicReview') }}</label>
          <template v-if="identityReviewRequired">
            <label><input v-model="confirmIdentityChanges" type="checkbox" /> {{ t('knowledgeFirst.confirmIdentityChanges') }}</label></template>
        </section>
        <section v-if="tab === 'tree'" class="tree-section">
          <div v-if="!treeOnly && displayTree?.teaching_assessment" class="notice" :class="{ stale: !displayTree.teaching_assessment.ready_for_adoption }">
            <strong>{{ t('knowledgeFirst.teachingRound') }}</strong><p>{{ t('knowledgeFirst.candidateWarning') }}</p>
            <p>{{ t('knowledgeFirst.capabilities') }} {{ displayTree.teaching_assessment.capability_units }} · {{ t('knowledgeFirst.masteryCriteria') }} {{ displayTree.teaching_assessment.criteria }} · {{ t('knowledgeFirst.mistakesAndRepair') }} {{ displayTree.teaching_assessment.new_mistakes }}</p>
            <p>{{ t('knowledgeFirst.wholePackagePass') }} {{ displayTree.teaching_assessment.semantic_passed_units }}/{{ displayTree.teaching_assessment.capability_units }}</p>
          </div>
          <div v-if="!treeOnly" class="section-heading"><div><h2>{{ t('knowledgeFirst.tree') }}</h2><p>{{ displayTree?.teaching_assessment ? t('knowledgeFirst.teachingProvenance') : displayTree?.provenance || data.provenance }}</p></div>
            <label v-if="historyOptions.length || selectedCandidate">{{ t('knowledgeFirst.version') }}<select v-model="treeChoice">
            <option v-if="treeChoice === 'candidate' && !selectedCandidate && data.tree" value="candidate" disabled>{{ t('knowledgeFirst.candidatePreparingBaseline') }}</option>
              <option v-if="selectedCandidate && selectedCandidate.revision_id !== data.knowledge_revision" value="candidate">{{ t('knowledgeFirst.candidate') }} · {{ short(selectedCandidate.revision_id) }}</option>
              <option v-for="v in historyOptions" :key="v.revision_id" :value="v.revision_id">{{ v.revision_id === data.knowledge_revision ? t('knowledgeFirst.current') : t('knowledgeFirst.history') }} · {{ short(v.revision_id) }}</option>
            </select></label></div>
          <div v-if="displayTree?.knowledge_points.length" class="tree-layout" :class="{ 'has-selection': !!selectedPoint }">
            <div class="knowledge-tree-surface">
              <div class="knowledge-tree-view-switch" role="group" :aria-label="t('knowledgeFirst.treeViewMode')">
                <button type="button" data-testid="knowledge-tree-view" :aria-pressed="treeViewMode === 'tree'" :class="{ active: treeViewMode === 'tree' }" @click="treeViewMode = 'tree'">{{ t('knowledgeFirst.hierarchyView') }}</button>
                <button type="button" data-testid="knowledge-relation-view" :aria-pressed="treeViewMode === 'graph'" :class="{ active: treeViewMode === 'graph' }" @click="treeViewMode = 'graph'">{{ t('knowledgeFirst.relationGraphView') }}<span v-if="relationGraphRelations.length"> · {{ relationGraphRelations.length }}</span></button>
              </div>
              <div v-if="treeViewMode === 'graph'">
                <p v-if="displayTree?.atomic_assessment?.relation_status === 'not_run'" class="notice" data-testid="knowledge-relations-not-run">{{ t('knowledgeFirst.relationsNotRun') }}</p>
                <KnowledgeRelationGraph :nodes="relationGraphNodes" :relations="relationGraphRelations" :candidate-view="treeChoice === 'candidate'" :selected-id="selectedId" @select="selectRelationNode" />
              </div>
              <KnowledgeMasteryTree v-else :content-tree="contentTree" :tree-revision="displayTree.revision_id" :show-mastery="false" :selected-id="selectedId" @select="selectGraphPoint" />
            </div>
            <aside v-if="selectedPoint" ref="detailPane" class="knowledge-detail-pane" tabindex="-1" :aria-label="t('knowledgeFirst.pointDetails')">
            <button v-if="!selectedSource" type="button" class="close-point-detail" @click="closePoint">{{ t('knowledgeFirst.backToTree') }}</button>
            <KnowledgeSourceReader v-if="selectedSource" :course-id="courseId" :tree-revision="displayTree.revision_id" :knowledge-id="selectedId" :source="selectedSource" @close="closeSource" />
            <article v-else-if="selectedPoint" :key="selectedId" class="point-card">
              <div class="point-topline"><span>{{ selectedPoint.key }}</span><span>{{ t('knowledgeFirst.atom') }}</span></div>
              <h2>{{ selectedPoint.name }}</h2><MarkdownRenderer class="claim" :content="selectedPoint.statement" />
              <p class="knowledge-extraction-method">{{ t(`knowledgeFirst.method_${selectedPoint.extraction_method || 'unspecified'}`) }}</p>
              <p v-if="selectedPoint.derivation_note">{{ selectedPoint.derivation_note }}</p>
              <KnowledgeTerms :point="selectedPoint" />
              <details v-if="selectedPoint.inventory_attachments?.length"><summary>{{ t('knowledgeFirst.inventoryAttachments') }}</summary><div v-for="item in selectedPoint.inventory_attachments" :key="item.key"><strong>{{ item.name }}</strong><p>{{ item.claim }}</p><blockquote v-for="(source,index) in item.sources" :key="index">{{ source.quote }}</blockquote></div></details>
              <template v-if="selectedPoint.conditions?.length"><h3>{{ t('knowledgeFirst.conditions') }}</h3><ul><li v-for="c in selectedPoint.conditions" :key="c">{{ c }}</li></ul></template>
              <template v-if="selectedPoint.meta_question || selectedPoint.meta_answer"><h3>{{ t('knowledgeFirst.question') }}</h3><MarkdownRenderer :content="selectedPoint.meta_question || ''" /><MarkdownRenderer :content="selectedPoint.meta_answer || ''" /></template>
              <h3>{{ t('knowledgeFirst.relations') }}</h3>
              <p v-if="!relations.length" class="muted">{{ t('knowledgeFirst.noRelation') }}</p>
              <div v-for="link in relatedLinks" :key="link.edge.id" class="relation">
                <span v-if="link.crossLesson" class="relation-scope">{{ t('knowledgeFirst.crossLessonLinks') }}</span>
                <button type="button" :disabled="!link.point" @click="navigateRelated({ lesson_id: link.lessonId, knowledge_id: link.id })">{{ link.crossLesson ? `${lessonLabels[link.lessonId] || link.lessonId} · ` : '' }}{{ link.point?.name || link.id }}</button>
                <p class="relation-direction">{{ t(link.edge.source_id === selectedId ? 'knowledgeFirst.outgoing' : 'knowledgeFirst.incoming') }} · {{ pointName(link.edge.source_id) }} → {{ pointName(link.edge.target_id) }} · {{ t(`knowledgeFirst.relationTypes.${link.edge.type}`, link.edge.type) }}</p>
                <p v-if="link.edge.reason">{{ link.edge.reason }}</p><ul v-if="link.edge.conditions?.length"><li v-for="condition in link.edge.conditions" :key="condition">{{ condition }}</li></ul>
                <KnowledgeRelationEvidence :edge="link.edge" />
                <MarkdownRenderer v-if="link.point?.statement" class="related-statement" :content="link.point.statement" />
              </div>
              <template v-if="!treeOnly || diagnoses.length"><h3>{{ t('knowledgeFirst.diagnosis') }}</h3><div v-for="d in diagnoses" :key="d.key"><p>A · {{ d.hypothesis_a }}</p><p>B · {{ d.hypothesis_b }}</p><p>{{ d.repair_a }}</p><p>{{ d.repair_b }}</p></div>
              <p v-if="!diagnoses.length" class="muted">{{ t(generic ? 'knowledgeFirst.genericNoDiagnosis' : 'knowledgeFirst.noDiagnosis') }}</p></template>
              <TeachingCapabilityPanel v-if="!treeOnly" :tree="displayTree" :point-id="selectedId" />
              <KnowledgeQuestionSupply v-if="!generic && data.can_edit && displayTree.revision_id === data.knowledge_revision" :course-id="courseId" :knowledge-id="selectedId" :baseline-revision="data.knowledge_revision" />
              <div v-for="source in selectedPoint.source_quotes" :key="source.evidence_id + source.quote" class="source-evidence">
                <template v-if="source.handout_ref"><div class="source-evidence-heading"><span>{{ t('knowledgeFirst.generatedHandout') }} · {{ lessonLabels[source.handout_ref.lesson_id] || source.handout_ref.lesson_id }} · {{ short(source.handout_ref.script_revision_id) }}</span><button v-if="data.can_edit" type="button" data-testid="locate-knowledge-source" @click="selectedSource = source">{{ t('knowledgeFirst.locateSource') }}</button></div><details><summary>{{ t('knowledgeFirst.readSourceText') }}</summary><blockquote><MarkdownRenderer :content="source.quote" /></blockquote></details></template>
                <blockquote v-else><MarkdownRenderer :content="source.quote" /></blockquote>
                <button v-if="!source.handout_ref && data.can_edit" type="button" data-testid="locate-knowledge-source" @click="selectedSource = source">{{ t('knowledgeFirst.locateSource') }}</button>
              </div>
              <h3>{{ t('knowledgeFirst.trace') }}</h3><dl><dt>ID</dt><dd>{{ selectedPoint.knowledge_id }}</dd><dt>{{ t('knowledgeFirst.version') }}</dt><dd>{{ selectedPoint.revision_id }}</dd><dt>{{ t('knowledgeFirst.source') }}</dt><dd>{{ selectedPoint.source_refs.join(', ') }}</dd></dl>
            </article>
            </aside>
          </div>
          <p v-else class="empty-card">{{ t(activeJob ? 'knowledgeFirst.treeGenerationInProgress' : blockingJobs.length ? 'knowledgeFirst.waitForSourceTask' : perLesson ? (selectedLesson?.can_generate ? 'knowledgeFirst.lessonTreeEmpty' : 'knowledgeFirst.lessonHandoutRequired') : derived ? (!data.can_generate_tree ? 'knowledgeFirst.handoutsRequired' : 'knowledgeFirst.noDerivedTree') : 'knowledgeFirst.noTree') }}</p>
          <div v-if="!treeOnly && treeChoice === 'candidate' && displayTree && data.can_edit && canAdoptSelection" class="adopt-bar"><p>{{ t(derived ? 'knowledgeFirst.derivedAdoptHint' : generic ? 'knowledgeFirst.genericAdoptHint' : displayTree.teaching_assessment ? 'knowledgeFirst.candidateWarning' : 'knowledgeFirst.adoptHint') }}</p>
            <button class="primary" :disabled="busy || activeJobs.length > 0 || staleTreeSource || displayTree.revision_id === data.knowledge_revision || displayTree.teaching_assessment?.ready_for_adoption === false || !atomicAdoptionReady" @click="adopt">{{ t('knowledgeFirst.adoptTree') }}</button></div>
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
              <template #aside><HandoutConceptMap class="handout-reading-aside" :sections="conceptSections" :target="handoutRoot" /></template>
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
import http, { activeIdentityHeaders, withApiBase } from '../utils/http'
import { consumeEventStream } from '../shared/generation-stream'
import { createUuid } from '../utils/client-id'
import { t } from '../shared/i18n'
import MarkdownRenderer from './MarkdownRenderer.vue'
import KnowledgeMasteryTree from './KnowledgeMasteryTree.vue'
import { createContentKnowledgeTree } from '../utils/knowledge-tree-layout'
import TeachingCapabilityPanel from './TeachingCapabilityPanel.vue'
import KnowledgeQuestionSupply from './KnowledgeQuestionSupply.vue'
import KnowledgeSourceReader from './KnowledgeSourceReader.vue'
import KnowledgeTerms from './KnowledgeTerms.vue'
import KnowledgeRelationEvidence from './KnowledgeRelationEvidence.vue'
import KnowledgeRelationGraph from './KnowledgeRelationGraph.vue'
import HandoutContentBlock from './HandoutContentBlock.vue'
import HandoutReadingGuide from './HandoutReadingGuide.vue'
import HandoutReadingLayout from './HandoutReadingLayout.vue'
import HandoutConceptMap from './HandoutConceptMap.vue'
import { buildHandoutConceptSections } from '../utils/handout-concepts'

const props = withDefaults(defineProps<{ courseId: string; treeOnly?: boolean; initialLessonId?: string }>(), { treeOnly: false, initialLessonId: '' })
const emit = defineEmits<{ updated: []; 'open-handouts': []; 'lesson-change': [id: string] }>()
const courseId = computed(() => props.courseId)
const knowledgeLessonId = ref(props.initialLessonId)
const data = ref<any>(null), error = ref(''), busy = ref(false)
const observationNotice = ref('')
const confirmIdentityChanges = ref(false), confirmAtomicReview = ref(false)
const confirmRelations = ref(false)
const selectedRelationIds = ref<string[]>([])
const generic = computed(() => data.value?.workflow === 'knowledge_first_generic_v1')
const inputs = reactive({ requirements: '', target_audience: '', lesson_count: 3, material_asset_ids: [] as string[] })
const inputDirty = ref(false), materials = ref<any[]>([]), handoutRoot = ref<HTMLElement | null>(null)
const tab = ref('tree'), treeChoice = ref(''), selectedId = ref(''), lesson = ref('types'), handoutChoice = ref('')
const treeViewMode = ref<'tree' | 'graph'>('tree')
const detailPane = ref<HTMLElement | null>(null)
const selectedSource = ref<any>(null)
let pointTrigger: HTMLElement | null = null
function selectGraphPoint(id: string, trigger: HTMLElement) { pointTrigger = trigger; selectedId.value = id }
function selectRelationNode(node: any) {
  if (displayTree.value?.knowledge_points.some((point: any) => point.knowledge_id === node.knowledge_id)) selectedId.value = node.knowledge_id
  else {
    const lessonId = node.section_ids.find((id: string) => lessonLabels.value[id])
    if (lessonId) void navigateRelated({ lesson_id: lessonId, knowledge_id: node.knowledge_id })
  }
}
async function closePoint() { selectedId.value = ''; await nextTick(); pointTrigger?.focus({ preventScroll: true }) }
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false, requestSequence = 0
let retryCount = 0, observationStopped = false
let readController: AbortController | undefined
let readInFlight = false
let streamController: AbortController | undefined
let streamKey = ''
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
function generationFailureMessage(job: any) {
  if (job.error?.code === 'AIRequestBudgetExceeded') return t('knowledgeFirst.inputBudgetExceeded')
  if (job.error?.code === 'ModelConnectionUnavailable') return t('knowledgeFirst.modelDisconnected')
  return job.error?.message
}
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
  const preview = (data.value?.generation_previews || []).find((p: any) => !perLesson.value || p.lesson_id === knowledgeLessonId.value)
  const pendingJob = activeJobs.value.find(j => j.id === preview?.job_id)
  if (preview && pendingJob) return preview
  if (!perLesson.value) return data.value?.candidate ? { tree: data.value.candidate, job_id: data.value.candidate_job_id, lesson_id: '' } : null
  const pending = (tree: any) => tree && !(data.value?.history || []).some((h: any) => h.revision_id === tree.revision_id)
  const candidates = (data.value?.candidates || []).filter((c: any) => !c.adopted && pending(c.tree) && (c.lesson_id || c.source_knowledge_revision === undefined || c.source_knowledge_revision === data.value.knowledge_revision))
  return candidates.find((c: any) => c.lesson_id === knowledgeLessonId.value)
    || candidates.find((c: any) => !c.lesson_id)
    || (!Array.isArray(data.value?.candidates) && pending(data.value?.candidate) && !data.value.candidate.scope_lesson_id ? { tree: data.value.candidate, job_id: data.value.candidate_job_id, lesson_id: '' } : null)
})
const selectedCandidate = computed(() => selectedCandidateRecord.value?.tree)
const atomicRun = computed(() => {
  if (treeChoice.value === 'candidate' && selectedCandidate.value?.relation_assessment) return null
  if (treeChoice.value && treeChoice.value !== 'candidate' && treeChoice.value !== data.value?.knowledge_revision) return null
  return (data.value?.atomic_runs || []).find((run:any) => !perLesson.value || run.lesson_id === knowledgeLessonId.value)
})
const progressJob = computed(() => {
  if (activeJob.value) return activeJob.value
  const run = relationRun.value || atomicRun.value
  const job = latestJob.value || (run ? { id: run.job_id, status: run.status, knowledge_lesson_id: run.lesson_id } : null)
  const adopted = [data.value?.tree, ...(data.value?.history || [])].some(tree => tree?.generation_job_id === job?.id)
    || run?.adopted && run.job_id === job?.id
  return job?.status === 'completed' && adopted ? null : job
})
const progressPercent = computed(() => {
  const job = progressJob.value
  if (!job) return 0
  if (job.status === 'completed') return 100
  const reported = Number(job.progress)
  if (Number.isFinite(reported) && reported > 0) return Math.min(99, Math.max(0, Math.round(reported)))
  const pipeline = atomicRun.value?.pipeline
  if (pipeline) {
    const fraction = (rows: any[] = []) => rows.length ? rows.filter(row => row.status === 'completed').length / rows.length : 0
    return Math.floor(20 * fraction(pipeline.inventory_batches) + (pipeline.organize_hierarchy ? 65 : 75) * fraction(pipeline.batches)
      + (pipeline.organize_hierarchy && pipeline.hierarchy?.status === 'completed' ? 10 : 0))
  }
  return job.phase === 'structure_check' ? 95 : job.phase === 'preparing' ? 5 : 0
})
const atomicCanContinue = computed(() => {
  const run = atomicRun.value, pipeline = run?.pipeline
  return Boolean(!activeJob.value && run && !run.adopted
    && ['failed', 'paused', 'cancelled'].includes(run.status)
    && (!pipeline?.batches?.length || [...(pipeline?.inventory_batches || []), ...(pipeline?.batches || [])].some((batch: any) => batch.status !== 'completed')
      || pipeline?.organize_hierarchy && pipeline.hierarchy?.status !== 'completed'
      || pipeline?.include_relations && pipeline.relations?.status !== 'completed'))
})
const relationOnlyContinue = computed(() => {
  const pipeline = atomicRun.value?.pipeline
  return Boolean(pipeline?.include_relations && pipeline.relations?.status !== 'completed'
    && [...(pipeline.inventory_batches || []), ...(pipeline.batches || [])].length
    && [...(pipeline.inventory_batches || []), ...(pipeline.batches || [])].every((batch: any) => batch.status === 'completed')
    && (!pipeline.organize_hierarchy || pipeline.hierarchy?.status === 'completed'))
})
const atomicCanOrganize = computed(() => {
  const run = atomicRun.value, pipeline = run?.pipeline
  return Boolean(!activeJob.value && run && !run.adopted
    && ['completed', 'failed', 'paused', 'cancelled'].includes(run.status)
    && pipeline?.batches?.length
    && pipeline.batches.every((batch: any) => batch.status === 'completed')
    && (pipeline?.hierarchy?.status !== 'completed' || pipeline.hierarchy.result?.schema_version !== 'knowledge_hierarchy_v5'))
})
const atomicCanRebuild = computed(() => !activeJob.value && atomicRun.value && !atomicRun.value.adopted
  && !['pending', 'running'].includes(atomicRun.value.status) && atomicRun.value.pipeline?.items?.length
  && selectedCandidate.value?.atomic_assessment?.ready_for_adoption === false)
const relationRun = computed(() => {
  if (treeChoice.value && treeChoice.value !== 'candidate' && treeChoice.value !== data.value?.knowledge_revision) return null
  return (data.value?.relation_runs || []).find((run:any)=>run.lesson_id === knowledgeLessonId.value)
})
const relationCanContinue = computed(() => !activeJob.value && relationRun.value && !relationRun.value.adopted
  && ['failed', 'paused', 'cancelled'].includes(relationRun.value.status))
const proposedRelations = computed(()=>(displayTree.value?.relations || []).filter((edge:any)=>(displayTree.value?.relation_assessment?.proposed_ids || []).includes(edge.id)))
const canGenerateRelations = computed(()=>treeChoice.value === data.value?.knowledge_revision && data.value?.tree?.status === 'accepted' && selectedLesson.value?.can_generate && data.value.tree.knowledge_points?.some((p:any)=>(p.section_refs || [p.topic]).includes(knowledgeLessonId.value)))
const atomicReviewRequired = computed(() => displayTree.value?.atomic_assessment?.issues?.some((issue:any)=>issue.severity === 'review'))
const identityReviewRequired = computed(() => !!displayTree.value?.identity_changes?.retired_points?.length)
const atomicAdoptionReady = computed(() => displayTree.value?.atomic_assessment?.ready_for_adoption !== false
  && !displayTree.value?.generation_preview
  && (!displayTree.value?.relation_assessment || displayTree.value.relation_assessment.ready_for_adoption && confirmRelations.value)
  && (!atomicReviewRequired.value || confirmAtomicReview.value) && (!identityReviewRequired.value || confirmIdentityChanges.value))
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
  const tree = treeChoice.value === 'candidate' ? (selectedCandidate.value || data.value?.tree) : data.value?.history.find((v: any) => v.revision_id === treeChoice.value)
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
function jobPhase(job: any) {
  const phase = job.status === 'pending' ? 'pending' : job.phase || 'model'
  const known = ['pending', 'preparing', 'model', 'model_wait', 'model_streaming', 'structure_check', 'completed', 'failed', 'cancelled', 'paused']
  const label = t(`knowledgeFirst.phase_${known.includes(phase) ? phase : 'model'}`)
  return job.pipeline_stage ? `${t(['relations','tree_relations'].includes(job.pipeline_stage) ? 'knowledgeFirst.relationCandidates' : job.pipeline_stage === 'hierarchy' ? 'knowledgeFirst.organizeHierarchy' : job.pipeline_stage === 'inventory' ? 'knowledgeFirst.inventoryTitle' : 'knowledgeFirst.atomicCandidates')} · ${label}` : label
}
const sourceComparison = computed(() => {
  if (!derived.value || !displayTree.value) return null
  const recordedSources = (displayTree.value.source_handouts || []) as { lesson_id?: string; key?: string; title?: string; script_revision_id?: string }[]
  const sources = recordedSources.filter(source => !perLesson.value || (source.lesson_id || source.key) === knowledgeLessonId.value).map(source => {
    const lessonId = source.lesson_id || source.key || ''
    const current = (data.value?.source_handouts || []).find((item: any) => (item.lesson_id || item.key) === lessonId)
    return { lessonId, title: lessonLabels.value[lessonId] || source.title || lessonId,
      recorded: source.script_revision_id || '', current: current?.script_revision_id || '' }
  })
  if (!sources.length) return null // Older material trees may have no handout provenance.
  return { sources, stale: sources.some(source => !source.recorded || !source.current || source.recorded !== source.current) }
})
const staleTreeSource = computed(() => Boolean(sourceComparison.value?.stale))
const contentTree = computed(() => createContentKnowledgeTree(
  `${courseId.value}:${perLesson.value ? knowledgeLessonId.value : ''}`,
  perLesson.value ? lessonLabels.value[knowledgeLessonId.value] || data.value?.title : data.value?.title,
  displayTree.value?.categories || [],
  displayTree.value?.knowledge_points || [],
))
const relationGraphNodes = computed(() => {
  const ids = new Set((displayTree.value?.knowledge_points || []).map((p: any) => p.knowledge_id))
  for (const edge of displayTree.value?.relations || []) { ids.add(edge.source_id); ids.add(edge.target_id) }
  return (displayTree.value?.allKnowledgePoints || []).filter((p: any) => ids.has(p.knowledge_id)).map((point: any, index: number) => ({
  knowledge_id: point.knowledge_id,
  code: point.key || `K${index + 1}`,
  parent_id: point.parent_id || null,
  node_type: 'knowledge_point',
  name: point.name,
  description: point.statement || '',
  depth: 0,
  sort_order: index,
  path_ids: [], path_names: [], aliases: point.aliases || [], learning_actions: [], typical_problems: [],
  section_ids: point.section_refs || [], block_ids: [], objective_ids: [], criterion_ids: [], question_ids: [], misconception_ids: [], skill_unit_ids: [], mistake_point_ids: [], improvement_ids: [], mastery_criterion_ids: [],
  statement: point.statement, conditions: point.conditions || [], boundaries: [], counterexamples: [], granularity_status: point.granularity_status,
  covered_by_course: true, source_status: point.source_status || (displayTree.value?.source_mode === 'handouts' ? 'handout_grounded' : ''), source_refs: point.source_refs || [], source_bindings: [], status: point.status || displayTree.value?.status || 'candidate', revision_id: point.revision_id || '',
  }))
})
const relationGraphRelations = computed(() => (displayTree.value?.relations || []).map((relation: any) => ({
  relation_id: relation.relation_id || relation.id,
  source_knowledge_id: relation.source_id,
  target_knowledge_id: relation.target_id,
  relation_type: relation.type || relation.relation_type || 'related',
  source_status: relation.source_status || '', source_refs: relation.source_refs || [], status: (displayTree.value?.relation_assessment?.proposed_ids || []).includes(relation.id) ? 'candidate' : relation.status || 'accepted', reason: relation.reason || '',
  conditions: relation.conditions || [], distinction: relation.distinction, derivation_steps: relation.derivation_steps || [], revision_id: relation.revision_id || '',
})))
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
watch([selectedId, selectedSource], async () => { await nextTick(); if (detailPane.value) detailPane.value.scrollTop = 0 })
watch([treeChoice, () => displayTree.value?.revision_id], () => { confirmIdentityChanges.value = false; confirmAtomicReview.value = false; confirmRelations.value = false; selectedRelationIds.value = [...(displayTree.value?.relation_assessment?.proposed_ids || [])] })
async function closeSource() { selectedSource.value = null; await nextTick(); detailPane.value?.focus({ preventScroll: true }) }
watch(() => [selectedId.value, treeChoice.value, courseId.value, knowledgeLessonId.value], () => { selectedSource.value = null })
watch(knowledgeLessonId, id => { selectedId.value = ''; chooseTreeVersion(); if (id) emit('lesson-change', id) })
watch(() => props.initialLessonId, id => { if (id && id !== knowledgeLessonId.value) knowledgeLessonId.value = id })
watch(() => [courseId.value, knowledgeLessonId.value, activeJob.value?.id], () => { void observeStream() })
async function observeStream() {
  const job = activeJob.value
  const key = job ? `${courseId.value}:${job.id}` : ''
  if (key === streamKey) return
  streamController?.abort(); streamKey = key
  if (!job || !data.value?.can_edit) return
  const controller = new AbortController(); streamController = controller
  const url = `${base.value}/events/${encodeURIComponent(job.id)}`
  try {
    const response = await fetch(withApiBase(url), { headers: activeIdentityHeaders({ Accept: 'text/event-stream' }), signal: controller.signal })
    if (!response.ok || !response.headers.get('Content-Type')?.includes('text/event-stream')) return
    await consumeEventStream(response, ({ event, data: eventData }) => {
      if (disposed || controller.signal.aborted || key !== streamKey) return
      const payload = eventData as any
      if (event === 'complete') { void refresh(); return }
      if (event !== 'snapshot' || payload.job_id !== job.id) return
      const current = data.value
      const jobs = (current.jobs || []).map((item: any) => item.id === job.id ? { ...item, ...payload.job } : item)
      const active = (current.active_jobs || []).map((item: any) => item.id === job.id ? { ...item, ...payload.job } : item)
      const previews = [...(current.generation_previews || []).filter((p: any) => p.job_id !== job.id)]
      if (payload.preview) previews.push({ job_id: job.id, lesson_id: job.knowledge_lesson_id, tree: payload.preview })
      else if (!('preview' in payload)) previews.push(...(current.generation_previews || []).filter((p: any) => p.job_id === job.id))
      data.value = { ...current, jobs, active_jobs: active, generation_previews: previews }
      if (payload.preview) treeChoice.value = 'candidate'
    })
  } catch { /* The existing status observer recovers connection failures. */ }
}
function scheduleObservation() {
  clearTimeout(timer)
  if (disposed || observationStopped || (data.value && !data.value.can_edit)) return
  const delay = retryCount ? Math.min(10000, 2000 * 2 ** Math.min(retryCount, 3)) : activeJobs.value.length ? 2000 : 10000
  timer = setTimeout(data.value ? pollStatus : refresh, delay)
}
function observationFailed(e: any) {
  const status = e?.response?.status
  if ([401, 403, 404].includes(status)) {
    if (data.value) data.value.can_edit = false
    observationStopped = true
    observationNotice.value = 'observationUnavailable'
  } else {
    retryCount++
    observationNotice.value = 'reconnectingStatus'
  }
}
async function pollStatus() {
  clearTimeout(timer)
  if (disposed || observationStopped) return
  if (busy.value) { scheduleObservation(); return }
  const seq = ++requestSequence
  readController?.abort()
  readController = new AbortController()
  readInFlight = true
  try {
    const { data: snapshot } = await http.get(`${base.value}/status`, { params: { source_mode: 'handouts' }, timeout: 10000, silentError: true, signal: readController.signal })
    if (disposed || seq !== requestSequence) return
    if (snapshot.can_edit === false) { data.value.can_edit = false; observationStopped = true; observationNotice.value = 'observationUnavailable'; return }
    retryCount = 0; observationNotice.value = ''
    if (snapshot.result_version !== data.value?.result_version) { await refresh(); return }
    const updates = new Map<string, any>((snapshot.jobs || []).map((job: any) => [job.id, job]))
    data.value = { ...data.value, can_edit: snapshot.can_edit ?? data.value.can_edit, active_jobs: snapshot.active_jobs || [],
      jobs: (data.value.jobs || []).map((job: any) => ({ ...job, ...(updates.get(job.id) || {}) })),
      blocking_job_ids: snapshot.blocking_job_ids || [],
      lesson_options: (data.value.lesson_options || []).map((option: any) => ({ ...option,
        blocking_job_ids: snapshot.lesson_blocking_job_ids?.[option.lesson_id] || [] })) }
  } catch (e) { if (!disposed && seq === requestSequence) observationFailed(e) }
  finally { if (!disposed && seq === requestSequence) { readInFlight = false; scheduleObservation() } }
}
async function refresh() {
  clearTimeout(timer)
  const seq = ++requestSequence
  readController?.abort()
  readController = new AbortController()
  readInFlight = true
  try {
    const response = await http.get(base.value, { params: { source_mode: 'handouts' }, timeout: 10000, silentError: true, signal: readController.signal })
    if (disposed || seq !== requestSequence) return
    const followLatest = !handoutChoice.value || handoutChoice.value === currentLesson.value?.current_revision_id
    data.value = response.data; error.value = ''; observationNotice.value = ''; retryCount = 0
    if (perLesson.value && !selectedLesson.value) knowledgeLessonId.value = lessonOptions.value[0]?.lesson_id || ''
    if (generic.value && !inputDirty.value && data.value.inputs) Object.assign(inputs, data.value.inputs)
    if (generic.value && !data.value.handouts.some((h: any) => h.topic === lesson.value)) lesson.value = data.value.handouts[0]?.topic || ''
    if (!treeChoice.value || (treeChoice.value === 'candidate' && !selectedCandidate.value && latestJob.value?.status === 'failed')) chooseTreeVersion()
    if (!selectedId.value && !props.treeOnly) selectedId.value = displayTree.value?.knowledge_points[0]?.knowledge_id || ''
    if (followLatest) handoutChoice.value = currentLesson.value?.current_revision_id || ''
  } catch (e) { if (!disposed && seq === requestSequence) { if (!data.value) error.value = message(e); observationFailed(e) } }
  finally { if (!disposed && seq === requestSequence) { readInFlight = false; scheduleObservation() } }
}
function retryObservation() { observationStopped = false; retryCount = 0; void (data.value ? pollStatus() : refresh()) }
function resumeObservation() { if (!observationStopped && !busy.value && !disposed && !readInFlight) void (data.value ? pollStatus() : refresh()) }
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
  await mutate(`generate/${topic}`, { request_id: createUuid(), ...(derived.value ? { source_mode: 'handouts' } : {}), ...(perLesson.value ? { lesson_id: knowledgeLessonId.value, pipeline: 'inventory_atomic_v1', organize_hierarchy: true, include_relations: true } : {}) })
}
async function continueAtomic(batchId = '') {
  if (!atomicRun.value) return
  treeChoice.value = 'candidate'
  await mutate('generate/tree', { request_id: createUuid(), source_mode:'handouts', lesson_id:knowledgeLessonId.value,
    pipeline:'inventory_atomic_v1', organize_hierarchy:true, resume_job_id:atomicRun.value.job_id, retry_batch_id:batchId })
}
async function generateRelations(resume = false, batchId = '') {
  if (resume && !relationRun.value) return
  treeChoice.value = 'candidate';tab.value = 'tree'
  await mutate('generate/tree',{request_id:createUuid(),source_mode:'handouts',lesson_id:knowledgeLessonId.value,
    pipeline:'knowledge_relations_v1',...(resume ? {resume_job_id:relationRun.value.job_id,retry_batch_id:batchId} : {})})
}
async function adopt() {
  if (!canAdoptSelection.value || staleTreeSource.value || !atomicAdoptionReady.value) return
  const confirmations = {
    ...(displayTree.value?.relation_assessment ? { confirm_relations: confirmRelations.value, selected_relation_ids: selectedRelationIds.value } : {}),
    ...(displayTree.value?.atomic_assessment ? { confirm_identity_changes: confirmIdentityChanges.value, confirm_atomic_review: confirmAtomicReview.value } : {}),
  }
  await mutate(`adopt/${selectedCandidateRecord.value.job_id}`, confirmations)
  if (!error.value) treeChoice.value = data.value.knowledge_revision
}
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
async function showSource(revision: string, id = '') { treeChoice.value = revision; selectedId.value = id; tab.value = 'tree'; await nextTick(); document.querySelector('.point-card')?.scrollIntoView({ block: 'start' }) }
watch(lesson, () => { handoutChoice.value = currentLesson.value?.current_revision_id || '' })
watch(displayTree, tree => { if (tree && !tree.knowledge_points.some((p: any) => p.knowledge_id === selectedId.value)) selectedId.value = props.treeOnly ? '' : tree.knowledge_points[0]?.knowledge_id || '' })
watch(courseId, () => { observationStopped = false; retryCount = 0; observationNotice.value = ''; knowledgeLessonId.value = props.initialLessonId; data.value = null; inputDirty.value = false; materials.value = []; treeChoice.value = ''; selectedId.value = ''; handoutChoice.value = ''; void refresh() })
watch(() => [generic.value, data.value?.enabled], () => { void loadMaterials() })
onMounted(() => { void refresh(); window.addEventListener('online', resumeObservation); window.addEventListener('focus', resumeObservation) })
onBeforeUnmount(() => { disposed = true; requestSequence++; readController?.abort(); streamController?.abort(); clearTimeout(timer); window.removeEventListener('online', resumeObservation); window.removeEventListener('focus', resumeObservation) })
</script>

<style scoped>
.relation-adoption>summary{min-height:28px;cursor:pointer;font-weight:600}
.relation-option{padding:8px 0;border-bottom:1px solid #e4def0}
.relation-explanation{margin:4px 0 0 24px}
.relation-explanation>summary{cursor:pointer;font-size:15px;color:#6a5289}
.relation-adoption summary:focus-visible{outline:3px solid #b3a1d1;outline-offset:3px}
.knowledge-workspace{max-width:1480px;margin:auto;padding:30px 36px 70px;color:#243454;font-size:15px}.knowledge-header,.section-heading,.toolbar{display:flex;justify-content:space-between;align-items:center;gap:24px}.knowledge-header h1{font-size:30px;letter-spacing:-.7px;margin:8px 0}.knowledge-header a{color:#5364bd;text-decoration:none}.eyebrow{font-size:13px;letter-spacing:2px;color:#777bb4;margin-top:24px}.knowledge-workspace p{line-height:1.8}.knowledge-workspace button,.knowledge-workspace select{font:inherit;border:1px solid #dfe4f1;border-radius:9px;padding:9px 14px;background:#fff;color:#465478;cursor:pointer}.knowledge-workspace button:disabled{opacity:.45;cursor:not-allowed}.knowledge-workspace button:focus-visible,.knowledge-workspace summary:focus-visible{outline:3px solid #9dacec;outline-offset:2px}.knowledge-workspace .primary{background:var(--lz-action-bg);border-color:var(--lz-action-border);color:var(--lz-action-text);border:1px solid var(--lz-action-border);border-radius:var(--lz-action-radius);box-shadow:var(--lz-action-shadow)}.steps{display:flex;list-style:none;padding:0;gap:12px;margin:28px 0}.steps li{flex:1;padding:16px 20px;background:#f0f2f8;border-radius:12px;color:#7c8499}.steps .done{background:#e8edfc;color:#475db6}.toolbar{margin:24px 0}.tabs{display:flex;gap:8px}.tabs .active,.lecture-nav .active{background:#e9edff;border-color:#b6c1ef;color:#4554a2}.section-heading h2{font-size:20px;margin:0}.section-heading p{font-size:14px;max-width:780px;color:#748097}.section-heading label{min-width:180px;font-size:14px}.section-heading select{display:block;width:100%;margin-top:6px}.tree-layout{display:grid;grid-template-columns:390px minmax(0,1fr);gap:24px;margin-top:18px;align-items:start}.tree-nav,.point-card,.lecture-nav,.handout-reader,.empty-card{background:white;border:1px solid #e2e7f2;border-radius:16px;padding:24px;box-shadow:0 6px 26px #35406d06}.tree-nav{max-height:75vh;overflow:auto;padding:20px}.tree-root{padding:4px 10px 22px;font-weight:700}.tree-root span{float:right;font-weight:400;font-size:13px;color:#7a849d}.tree-nav summary{cursor:pointer;padding:12px 4px;line-height:1.5}.tree-group{border-left:1px solid #dfe4f1;margin-left:8px;padding-left:14px}.tree-group summary{font-size:14px;color:#697496}.tree-nav button{display:flex;align-items:center;gap:10px;text-align:left;width:100%;border:0;background:transparent;padding:9px 10px;line-height:1.5}.tree-nav button.selected{background:#edf0ff;color:#4c5baf}.leaf-dot{height:6px;width:6px;flex-shrink:0;border-radius:50%;background:#a0abdb}.point-card{padding:30px;min-height:500px}.point-topline{display:flex;justify-content:space-between;color:#8791ad;font-size:13px}.point-card h2{font-size:25px}.claim{background:#f4f6fc;border-left:3px solid #8d9cdc;padding:18px;border-radius:5px}.point-card h3{margin-top:28px;font-size:16px}.point-card li{margin:8px 0;line-height:1.7}.point-card dl{font-size:13px;display:grid;grid-template-columns:65px 1fr;gap:10px;overflow-wrap:anywhere}.point-card dd{margin:0}.muted{color:#818ba1;font-size:14px}.relation{padding:14px;background:#f7f8fd;border-radius:10px}.adopt-bar{display:flex;align-items:center;justify-content:space-between;padding:20px;margin-top:20px;background:#ebeffe;border-radius:14px}.notice{padding:16px 20px;background:#edf2fe;border-radius:12px;margin:18px 0;line-height:1.8}.error{background:#fff0ee;color:#a94334}.stale{background:#fff4da}.job{display:flex;gap:20px;align-items:center}.job span{flex:1;font-size:13px}.notice pre{white-space:pre-wrap;max-height:240px;overflow:auto}.handout-layout{display:grid;grid-template-columns:255px minmax(0,1fr);gap:24px;align-items:start}.lecture-nav button{display:block;text-align:left;width:100%;margin:12px 0;line-height:1.7}.lecture-nav small{display:block;color:#929bb1}.handout-reader{padding:30px 38px;min-height:400px}.reading-block{border-bottom:1px solid #edf0f6;padding:18px 0 26px;line-height:1.9}.reading-block h3{font-size:19px}.ref-chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}.ref-chips button{font-size:12px;padding:4px 9px;color:#6474b5;background:#f4f6fd;border:0}code{overflow-wrap:anywhere}@media(max-width:1050px){.knowledge-workspace{padding:22px}.tree-layout{grid-template-columns:310px minmax(0,1fr)}.section-heading{align-items:flex-start}.handout-layout{grid-template-columns:210px minmax(0,1fr)}}
@media(max-width:900px){.knowledge-workspace{padding:20px 14px;min-width:0;width:100%;box-sizing:border-box}.knowledge-header,.section-heading,.toolbar,.adopt-bar,.job{flex-wrap:wrap;gap:12px}.knowledge-header h1{font-size:24px}.steps{flex-direction:column}.steps li{padding:12px 16px}.tree-layout,.handout-layout{grid-template-columns:minmax(0,1fr)}.tree-nav{max-height:330px}.point-card,.handout-reader{padding:20px;min-width:0}.point-card h2{font-size:22px;overflow-wrap:anywhere}.handout-reader pre{max-width:100%;overflow:auto}.lecture-nav{padding:16px}.section-heading label{min-width:0;width:100%}.tabs{flex-wrap:wrap}.knowledge-workspace button{overflow-wrap:anywhere}.job span{overflow-wrap:anywhere}.point-card dl{grid-template-columns:50px minmax(0,1fr)}}
</style>

<style scoped>
.teacher-knowledge-manager { width:100%; max-width:none; margin:0; padding:4px 8px 32px; box-sizing:border-box; }
.manager-tools { display:flex; align-items:center; justify-content:space-between; gap:16px; color:#8a789a; font-size:14px; }.teacher-knowledge-manager .toolbar { margin:18px 0; }.teacher-knowledge-manager .point-card { padding:24px; }
@media(max-width:900px) { .teacher-knowledge-manager .tree-layout { grid-template-columns:minmax(0,1fr); } }
</style>

<style scoped>
.generic-inputs form{display:grid;gap:16px;margin-top:16px}.generic-inputs label{display:grid;gap:6px;font-size:15px}.generic-inputs textarea,.generic-inputs input:not([type=checkbox]):not([type=file]){width:100%;box-sizing:border-box;padding:10px;border:1px solid #cbd2e5;border-radius:8px;background:white;font:inherit;color:inherit}.input-row{display:grid;grid-template-columns:1fr 140px;gap:18px}.generic-inputs .material-choice{display:flex;align-items:center;gap:8px}.saved-inputs{color:#39634a}.point-card blockquote{margin:12px 0;padding:12px 16px;border-left:3px solid #a69aca;background:#f5f2fa;font-size:15px;line-height:1.7}
</style>

<style scoped>
.handout-source-panel{margin:18px 0 24px;padding:24px;border:1px solid #e2e5f1;border-radius:14px;background:linear-gradient(120deg,#fafaff,#fff)}.source-panel-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:24px}.source-eyebrow{color:#6965ae;font-size:15px}.source-panel-heading h2{margin:8px 0;font-size:22px}.source-panel-heading p{margin:0;max-width:680px;color:#718099;font-size:15px}.source-count{white-space:nowrap;border:1px solid #e2def4;padding:6px 12px;border-radius:20px;color:#645a9b;font-size:15px}.source-steps{display:flex;list-style:none;gap:12px;padding:0;margin:22px 0;color:#8791a6;font-size:15px}.source-steps li+li:before{content:'›';padding-right:12px;color:#b5bccd}.source-steps .current{color:#5b58a6;font-weight:600}.source-empty{padding:14px 18px;background:#f3f4fa;border-radius:8px;color:#67738b}.source-list{margin:16px 0;font-size:15px}.source-list summary{cursor:pointer;color:#667290}.source-list ul{padding:0;list-style:none}.source-list li{display:flex;justify-content:space-between;gap:16px;padding:10px 0;border-bottom:1px solid #edf0f6}.source-list span{font-size:13px;color:#8991a5}.toolbar:has(>.primary:only-child){justify-content:flex-end}.point-card blockquote footer{margin-top:10px;font-size:13px;color:#8892a7;overflow-wrap:anywhere}
</style>

<style scoped>
.source-evidence{margin-top:20px}.source-evidence-heading{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;font-size:14px;color:#7c849b}.source-evidence summary{font-size:15px;cursor:pointer;color:#697496;margin-top:10px}.source-evidence blockquote{overflow-wrap:anywhere}.handout-reader{container-type:inline-size;min-width:0}.handout-reader :deep(.handout-reading-body){width:100%;box-sizing:border-box}.source-steps{flex-wrap:wrap}
</style>

<style scoped>
.tree-only{padding:0;max-width:none}.tree-only .toolbar{margin:0 0 20px;gap:12px;flex-wrap:wrap}.tree-only .toolbar h2{flex:1;margin:0;font-size:24px;color:#343b70}.tree-version{display:flex;align-items:center;gap:8px;color:#7c849b;font-size:14px}.tree-version select{max-width:260px}.tree-only .tree-layout{margin:0}.tree-only .notice{margin:0 0 18px}
</style>

<style scoped>
.knowledge-lesson-switch{display:flex;align-items:center;justify-content:center;gap:12px;margin:0 0 20px}.knowledge-lesson-switch select{min-width:0;max-width:560px;flex:1}.knowledge-lesson-switch button{white-space:nowrap}
</style>

<style scoped>
.knowledge-detail-pane{min-width:0}.tree-only .knowledge-detail-pane{position:sticky;top:0;max-height:calc(100dvh - 230px);overflow:auto;scrollbar-gutter:stable;border:1px solid #e2e7f2;border-radius:12px;background:#fff}.tree-only .point-card{min-height:0;border:0;box-shadow:none;border-radius:0;padding:24px}.tree-only .point-card h2{font-size:22px;line-height:1.5;margin:14px 0}.relation+.relation{margin-top:12px}.relation button{font-weight:600;text-align:left;line-height:1.6}.relation-scope{display:block;color:#7866a9;font-size:13px;margin-bottom:8px}.relation-direction{color:#697496;font-size:14px;line-height:1.6}.related-statement{border-top:1px solid #e3e7f2;padding-top:10px;margin-top:10px;font-size:15px}.tree-only .point-card :deep(.markdown-body){overflow-wrap:anywhere}.tree-only .point-card dl{font-size:13px}.tree-only .source-evidence-heading{line-height:1.7}
@media(max-width:1050px){.tree-only .point-card{padding:20px}}
.teacher-knowledge-manager{container-type:inline-size}
.generation-progress{display:block;border-left:3px solid #8b7ab7;background:#f7f5fc;padding:16px 18px}
.generation-progress-heading,.generation-progress-meta{display:flex;align-items:center;justify-content:space-between;gap:16px;font-size:15px;line-height:1.6}
.generation-progress-percent{font-size:20px;color:#5e4580;white-space:nowrap}
.generation-progress-track{height:10px;margin:12px 0 7px;overflow:hidden;border-radius:999px;background:#e5e0f1}
.generation-progress-track span{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#7662d8,#a78be7);transition:width .3s ease}
.generation-progress-meta{color:#766a88;font-size:14px}
.generation-progress-message{margin:8px 0 0;overflow-wrap:anywhere;font-size:14px}
.generation-progress-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.generation-progress-actions button{font:inherit;padding:6px 11px;border:1px solid #d8cde8;border-radius:7px;background:#fff;color:#654d82;cursor:pointer}
.generation-progress-actions button:disabled{opacity:.5;cursor:not-allowed}
.observation-notice{display:flex;align-items:center;justify-content:space-between;gap:16px;font-size:15px;background:#fff8eb}
.source-version-warning{margin:0 0 18px}
.teacher-knowledge-manager .tree-layout{position:relative;display:grid;grid-template-columns:minmax(0,1fr);gap:20px;align-items:start}
.teacher-knowledge-manager .tree-layout.has-selection{grid-template-columns:minmax(0,1fr) minmax(340px,400px)}
.tree-layout>.mastery-tree{min-width:0}.knowledge-tree-surface{min-width:0}.knowledge-tree-view-switch{display:flex;gap:6px;margin:0 0 10px;padding:4px;border:1px solid #e3deef;border-radius:10px;background:#faf9fd;width:max-content}.knowledge-tree-view-switch button{padding:7px 12px;border:0;border-radius:7px;background:transparent;color:#7a6a8d;font-size:14px}.knowledge-tree-view-switch button.active{background:#fff;color:#5e4580;box-shadow:0 1px 5px #68488716}.knowledge-tree-view-switch button:disabled{opacity:.45;cursor:not-allowed}.knowledge-tree-surface>.mastery-tree,.knowledge-tree-surface>.knowledge-relation-graph{min-width:0}
.close-point-detail{margin:16px 24px 0;font-size:15px}
@container(max-width:1000px){.teacher-knowledge-manager .tree-layout.has-selection{grid-template-columns:minmax(0,1fr)}.teacher-knowledge-manager .knowledge-detail-pane{position:absolute;z-index:5;top:0;right:0;width:min(420px,100%);max-height:clamp(420px,65vh,760px);overflow:auto;border:1px solid #ded3ed;border-radius:12px;background:#fff;box-shadow:-12px 12px 32px #4e396e20}}
</style>
