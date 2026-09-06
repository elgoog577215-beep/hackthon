<template>
  <Teleport to="body" :disabled="standalone">
    <Transition name="course-change-layer">
      <div v-if="modelValue" class="course-change-layer" :class="{ 'is-standalone': standalone, 'is-update-center': embeddedInCenter }" @keydown="handleKeydown">
        <button v-if="!standalone" type="button" class="course-change-backdrop" :aria-label="t('courseEvolution.workspace.close', '关闭课程修改工作台')" @click="close" />
        <section ref="workspaceRef" class="course-change-workspace" :role="standalone ? 'region' : 'dialog'" :aria-modal="standalone ? undefined : 'true'" :aria-labelledby="titleId" tabindex="-1">
          <header class="workspace-header">
            <span class="workspace-mark"><GitBranchPlus :size="19" /></span>
            <div class="workspace-title"><small>{{ t('courseEvolution.workspace.kicker', '课程发布后维护') }}</small><h2 :id="titleId">{{ t('courseEvolution.workspace.title', '全课联动修改') }}</h2></div>
            <div class="course-identity" :title="courseLabel"><BookOpenText :size="15" /><span>{{ courseLabel }}</span></div>
            <button type="button" class="icon-action" :title="t('courseEvolution.workspace.refresh', '重新读取课程资产')" :aria-label="t('courseEvolution.workspace.refresh', '重新读取课程资产')" :disabled="store.loading || store.contextLoading" @click="reloadWorkspace"><RefreshCw :size="17" :class="{ spinning: store.loading || store.contextLoading }" /></button>
            <button type="button" class="icon-action" :title="standalone ? t('courseEvolution.workspace.backToCourse', '返回课程工作台') : t('courseEvolution.workspace.close', '关闭课程修改工作台')" :aria-label="standalone ? t('courseEvolution.workspace.backToCourse', '返回课程工作台') : t('courseEvolution.workspace.close', '关闭课程修改工作台')" @click="close"><ArrowLeft v-if="standalone" :size="19" /><X v-else :size="19" /></button>
          </header>

          <nav class="journey" :aria-label="t('courseEvolution.workspace.journeyLabel', '课程修改流程')">
            <ol>
              <li v-for="step in journeySteps" :key="step.index" :class="{ active: step.index === currentJourneyStep, complete: step.index < currentJourneyStep }" :aria-current="step.index === currentJourneyStep ? 'step' : undefined">
                <span><Check v-if="step.index < currentJourneyStep" :size="13" /><template v-else>{{ step.index }}</template></span><b>{{ step.label }}</b>
              </li>
            </ol>
          </nav>

          <div v-if="workspaceState !== 'request' && workspaceState !== 'scanning'" class="workspace-context-stack">
            <section class="request-context">
              <div><small>{{ t('courseEvolution.workspace.currentGoal', '本次目标') }}</small><p :title="rawRequest">{{ rawRequest }}</p></div>
              <span>{{ changeKindLabel }}</span>
              <button v-if="workspaceState !== 'applied'" type="button" @click="openCorrection"><PencilLine :size="14" />{{ t('courseEvolution.workspace.adjustUnderstanding', '修正理解') }}</button>
            </section>

            <form v-if="correctionOpen" class="correction-bar" @submit.prevent="submitCorrection">
              <label><span>{{ t('courseEvolution.workspace.correctionLabel', '直接指出哪里理解错了') }}</span><textarea v-model="correctionText" rows="2" :placeholder="t('courseEvolution.workspace.correctionPlaceholder', '例如：不是删除案例，而是移到新章节，并保留原始资料。')" /></label>
              <div><button type="button" class="button-quiet" @click="correctionOpen = false">{{ t('common.cancel', '取消') }}</button><button type="submit" class="button-primary" :disabled="store.generating || !correctionText.trim()"><LoaderCircle v-if="store.generating" :size="15" class="spinning" /><Sparkles v-else :size="15" />{{ t('courseEvolution.workspace.submitCorrection', '重新分析') }}</button></div>
            </form>
            <p v-if="actionError" class="workspace-status-error" role="alert"><TriangleAlert :size="15" />{{ actionError }}</p>
          </div>

          <p v-if="store.progressDisconnected" class="workspace-status-error" role="status">{{ t('courseEvolution.workspace.progressDisconnected') }}</p>
          <p v-if="candidatesGenerating" class="workspace-status-progress" role="status"><LoaderCircle :size="16" class="spinning" />{{ t('courseEvolution.workspace.durableProgress') }}</p>
          <p v-if="focusedPlan?.impact_summary?.generation_error" class="workspace-status-error" role="alert">{{ focusedPlan.impact_summary.generation_error }}</p>
          <p v-if="coverage && workspaceState !== 'request' && workspaceState !== 'scanning'" class="coverage-status">{{ t('courseEvolution.workspace.scanCoverage').replace('{done}', String(coverage.scanned_units ?? coverage.ranked_candidates ?? 0)).replace('{total}', String(coverage.indexed_units || 0)) }}</p>
          <div class="workspace-stage">
            <main v-if="workspaceState === 'request'" class="request-state">
              <section class="readiness-strip" aria-live="polite">
                <header>
                  <span :data-ready="Boolean(context?.ready)"><LoaderCircle v-if="store.contextLoading" :size="16" class="spinning" /><CircleCheckBig v-else-if="context?.ready" :size="16" /><TriangleAlert v-else :size="16" /></span>
                  <div><small>{{ t('courseEvolution.workspace.courseReadiness', '课程准备情况') }}</small><strong>{{ contextStatusTitle }}</strong></div>
                  <b>{{ readyAssetCount }}/{{ contextAssets.length }}</b>
                </header>
                <ul><li v-for="asset in contextAssets" :key="asset.asset_type" :data-state="asset.state"><i /><span>{{ assetLabel(asset.asset_type) }}</span><small>{{ assetStateLabel(asset.state) }}</small></li></ul>
              </section>
              <section class="request-composer">
                <div class="request-heading"><h3>{{ t('courseEvolution.workspace.requestTitle', '这次想让课程怎么变？') }}</h3></div>
                <form @submit.prevent="submitRequest">
                  <div class="request-modes" role="group" :aria-label="t('courseEvolution.workspace.changeMode')">
                    <button v-for="mode in (['describe', 'replace', 'structure'] as const)" :key="mode" type="button" class="button-secondary" :aria-pressed="requestMode === mode" @click="requestMode = mode">{{ t(`courseEvolution.workspace.mode_${mode}`) }}</button>
                  </div>
                  <div v-if="requestMode === 'replace'" class="literal-replacement">
                    <label>{{ t('courseEvolution.workspace.findText') }}<input v-model="findText" type="text" maxlength="2000" /></label>
                    <label>{{ t('courseEvolution.workspace.replaceWith') }}<input v-model="replacementText" type="text" maxlength="2000" /></label>
                    <fieldset><legend>{{ t('courseEvolution.workspace.replaceScope') }}</legend><label v-for="asset in contextAssets.filter(a => ['outline', 'lesson_plan', 'script', 'course_content'].includes(a.asset_type))" :key="asset.asset_type"><input v-model="requestAssetTypes" type="checkbox" :value="asset.asset_type" />{{ assetLabel(asset.asset_type) }}</label></fieldset>
                  </div>
                  <textarea v-else-if="requestMode === 'describe'" ref="requestInputRef" v-model="requestText" rows="4" :placeholder="t('courseEvolution.workspace.requestPlaceholder', '例如：以后所有例子都讲得更详细一点，并同步更新讲义和 PPT')" :disabled="store.generating || contextUnavailable" />
                  <div v-if="requestMode === 'describe'" class="request-suggestions" :aria-label="t('courseEvolution.workspace.requestSuggestionsLabel', '常用修改示例')"><button v-for="item in requestSuggestions" :key="item" type="button" @click="requestText = item">{{ item }}</button></div>
                  <p v-if="store.generationError || actionError" class="inline-error" role="alert"><TriangleAlert :size="15" />{{ store.generationError || actionError }}</p>
                  <footer><button type="submit" class="button-primary button-submit" :disabled="store.generating || !requestCanSubmit || contextUnavailable"><Sparkles :size="16" />{{ t('courseEvolution.workspace.startAnalysis', '分析全课影响') }}</button></footer>
                </form>
              </section>
              <section ref="historyRef" class="recent-changes">
                <header><History :size="16" /><strong>{{ t('courseEvolution.workspace.recentChanges', '最近修改') }}</strong></header>
                <ol v-if="recentPlans.length"><li v-for="plan in recentPlans" :key="plan.change_set_id"><span :data-status="plan.status">{{ recentPlanStatus(plan) }}</span><button type="button" @click="openPlan(plan.change_set_id)"><b>{{ plan.request_text }}</b><small>{{ formatPlanTime(plan) }}</small></button></li></ol>
                <p v-else>{{ t('courseEvolution.workspace.noRecentChanges', '还没有课程修改记录') }}</p>
              </section>
            </main>

            <main v-else-if="workspaceState === 'scanning'" class="scanning-state" aria-live="polite">
              <section class="scan-main">
                <div class="scan-heading"><span><ScanSearch :size="21" /></span><div><small>{{ t('courseEvolution.workspace.scanningKicker', '正在分析全课') }}</small><h3>{{ t('courseEvolution.workspace.scanRequestTitle', '正在理解要求并定位所有受影响内容') }}</h3></div></div>
                <div class="scan-line"><span /></div>
                <dl><div><dt>{{ t('courseEvolution.workspace.scanIndex', '索引召回') }}</dt><dd>{{ context?.summary?.indexed_units || 0 }} {{ t('courseEvolution.workspace.units', '个单元') }}</dd></div><div><dt>{{ t('courseEvolution.workspace.scanRelations', '关系扩展') }}</dt><dd>{{ t('courseEvolution.workspace.crossAssets', '跨大纲与教学资产') }}</dd></div><div><dt>{{ t('courseEvolution.workspace.scanJudgement', 'AI 判断') }}</dt><dd>{{ t('courseEvolution.workspace.keepRealImpact', '保留真实影响') }}</dd></div></dl>
                <p><ShieldCheck :size="15" />{{ t('courseEvolution.workspace.scanGuard', '此阶段只建立影响计划，不写入正式课程。') }}</p>
              </section>
              <aside><header>{{ t('courseEvolution.workspace.scanningAssets', '正在检查') }}</header><ul><li v-for="(asset, index) in availableContextAssets" :key="asset.asset_type" :style="{ '--scan-delay': `${index * 90}ms` }"><component :is="assetIcon(asset.asset_type)" :size="16" /><span>{{ assetLabel(asset.asset_type) }}</span><Check :size="14" /></li></ul></aside>
            </main>

            <main v-else-if="workspaceState === 'interpreting'" class="clarification-state">
              <section><div class="clarification-heading"><BrainCircuit :size="22" /><div><small>{{ t('courseEvolution.workspace.interpretingKicker', 'AI 已完成初步理解') }}</small><h3>{{ interpretedGoal }}</h3></div></div><p>{{ t('courseEvolution.workspace.clarificationHint', '结构变化会影响大量内容，下面的信息需要先确认。') }}</p><ol><li v-for="question in planning?.intent.blocking_questions || []" :key="question">{{ question }}</li></ol><button type="button" class="button-primary" @click="openCorrection"><PencilLine :size="15" />{{ t('courseEvolution.workspace.answerAndReanalyze', '补充说明并重新分析') }}</button></section>
            </main>

            <div v-else-if="workspaceState === 'content'" class="review-layout">
              <aside class="impact-nav">
                <header><small>{{ t('courseEvolution.workspace.impactScope', '影响范围') }}</small><strong>{{ affectedUnits.length }} {{ impactUnitNoun }}</strong><p>{{ analysisModeLabel }}</p></header>
                <nav><button v-for="asset in affectedAssets" :key="asset.key" type="button" :class="{ active: selectedAsset === asset.key }" @click="selectedAsset = asset.key"><component :is="assetIcon(asset.key)" :size="16" /><span>{{ asset.label }}</span><b>{{ asset.count }}</b></button></nav>
                <section v-if="protectedRequirements.length" class="protected-scope"><ShieldCheck :size="16" /><div><b>{{ t('courseEvolution.workspace.protectedRequirements', '必须保留') }}</b><p>{{ protectedRequirements.join(listSeparator) }}</p></div></section>
                <dl class="scope-counts"><div><dt>{{ t('courseEvolution.workspace.included', '纳入') }}</dt><dd>{{ selectedImpactCount }}</dd></div><div><dt>{{ t('courseEvolution.workspace.excluded', '排除') }}</dt><dd>{{ excludedUnitIds.size }}</dd></div></dl>
              </aside>
              <section class="impact-review">
                <header class="review-header"><div><small>{{ t('courseEvolution.workspace.expectedImpact', '预计影响') }} · {{ selectedAssetLabel }}</small><h3>{{ reviewImpactTitle }}</h3></div><span><ShieldCheck :size="13" />{{ candidateReviewReady ? t('courseEvolution.workspace.candidatesReady', '修改候选已就绪') : candidatesGenerating ? t('courseEvolution.workspace.generatingCandidates', '正在形成具体修改方案') : t('courseEvolution.workspace.noCandidatesYet', '尚未生成修改候选') }}</span></header>
                <div class="impact-tools">
                  <label><Search :size="14" /><input v-model="impactQuery" type="search" :placeholder="t('courseEvolution.workspace.searchAffected', '搜索标题、内容或原因')" /></label>
                  <select v-model="selectedSection" :aria-label="t('courseEvolution.workspace.filterBySection', '按章节筛选')"><option value="">{{ t('courseEvolution.workspace.allSections', '全部章节') }}</option><option v-for="section in affectedSections" :key="section.id" :value="section.id">{{ section.label }}</option></select>
                  <span>{{ visibleAffectedUnits.length }} {{ t('courseEvolution.workspace.visibleItems', '项') }}</span>
                  <button type="button" class="button-quiet compact-action" :disabled="!visibleAffectedUnits.length" @click="selectVisibleUnits(true)">{{ t('courseEvolution.workspace.includeVisible', '纳入当前结果') }}</button>
                  <button type="button" class="button-quiet compact-action" :disabled="!visibleAffectedUnits.length" @click="selectVisibleUnits(false)">{{ t('courseEvolution.workspace.excludeVisible', '排除当前结果') }}</button>
                </div>
                <div class="impact-list">
                  <article v-for="item in visibleAffectedUnits" :key="item.migration_id" :class="{ excluded: !isUnitSelected(item.migration_id) }">
                    <label class="impact-check"><input type="checkbox" :checked="isUnitSelected(item.migration_id)" @change="toggleUnit(item.migration_id)" /><span /></label>
                    <div class="impact-copy"><header><div><small>{{ assetLabel(item.asset_type) }}</small><h4>{{ item.title }}</h4></div><label class="disposition-control"><span>{{ t('courseEvolution.workspace.handlingMethod', '处理方式') }}</span><select :value="effectiveDisposition(item)" @change="setDisposition(item, ($event.target as HTMLSelectElement).value)"><option v-for="option in dispositionOptions(item)" :key="option.value" :value="option.value">{{ option.label }}</option></select></label></header><p class="impact-reason">{{ item.reason }}</p><div v-if="(item.after_content || item.after_preview) && item.candidate_status === 'ready'" class="candidate-diff"><section class="source-preview"><small>{{ t('courseEvolution.workspace.beforeChange', '修改前') }}</small><p>{{ item.before_content || item.before_preview }}</p></section><ArrowRight :size="16" /><section class="source-preview is-after"><small>{{ t('courseEvolution.workspace.afterChange', '修改后') }}</small><p>{{ item.after_content || item.after_preview }}</p></section></div><section v-else-if="item.before_preview" class="source-preview"><small>{{ t('courseEvolution.workspace.currentSource', '当前内容摘录') }}</small><p>{{ item.before_content || item.before_preview }}</p></section><p v-if="item.candidate_error" class="candidate-error"><TriangleAlert :size="13" />{{ item.candidate_error }}<button v-if="item.candidate_error_detail?.retryable !== false" type="button" :disabled="candidatesGenerating" @click="retryCandidateFailures">{{ t('courseEvolution.workspace.retryThisFailure', '重试失败项') }}</button><button v-else type="button" @click="openCorrection">{{ t('courseEvolution.workspace.answerAndReanalyze') }}</button></p><footer><span v-if="item.source_state === 'stale'"><TriangleAlert :size="13" />{{ t('courseEvolution.workspace.sourceStale', '来源已落后于上游') }}</span><span v-else-if="item.operation_id && candidateReviewReady"><CircleCheckBig :size="13" />{{ item.change_count }} {{ t('courseEvolution.workspace.exactChanges', '处精确修改') }}</span><span>{{ confidenceLabel(item.confidence) }}</span></footer></div>
                  </article>
                  <p v-if="!visibleAffectedUnits.length" class="empty-impact">{{ t('courseEvolution.workspace.noAffectedForAsset', '这一类资产没有被判定为必改内容。') }}</p>
                </div>
                <footer class="review-actionbar"><div><strong v-if="scopeSaved && !reviewDirty"><CircleCheckBig :size="16" />{{ t('courseEvolution.workspace.scopeConfirmed', '预计影响已确认') }}</strong><strong v-else-if="reviewDirty"><PencilLine :size="16" />{{ t('courseEvolution.workspace.reviewEdited', '已调整，候选需要更新') }}</strong><p>{{ candidateReviewReady ? t('courseEvolution.workspace.applyBoundary', '只应用勾选且已形成精确候选的项目；其余内容保持不变。') : t('courseEvolution.workspace.reviewBoundary', '确认影响范围后才会生成具体修改方案；当前正式课程没有变化。') }}</p></div><button type="button" class="button-danger" :disabled="store.actingId === focusedPlan?.change_set_id" @click="discardPlan">{{ discardConfirm ? t('courseEvolution.workspace.confirmDiscard', '再次点击确认放弃') : t('courseEvolution.workspace.discardPlan', '放弃方案') }}</button><button v-if="hasRetryableCandidateFailures && !reviewDirty" type="button" class="button-secondary" :disabled="candidatesGenerating || store.actingId === focusedPlan?.change_set_id" @click="retryCandidateFailures"><RefreshCw :size="14" />{{ t('courseEvolution.workspace.retryFailedOnly', '只重试失败项') }}</button><button v-if="candidateReviewReady" type="button" class="button-primary" :disabled="candidatesGenerating || store.actingId === focusedPlan?.change_set_id || selectedApplicableCount === 0" @click="applyCourseChange"><LoaderCircle v-if="store.actingId === focusedPlan?.change_set_id" :size="15" class="spinning" /><Check v-else :size="15" />{{ applySelectedLabel }}</button><button v-else-if="hasNonRetryableCandidateFailures && !reviewDirty" type="button" class="button-primary" @click="openCorrection">{{ t('courseEvolution.workspace.answerAndReanalyze') }}</button><button v-else type="button" class="button-primary" :disabled="candidatesGenerating || store.actingId === focusedPlan?.change_set_id || selectedImpactCount === 0" @click="saveScopeReview"><LoaderCircle v-if="store.actingId === focusedPlan?.change_set_id" :size="15" class="spinning" /><Check v-else :size="15" />{{ scopeSaved ? t('courseEvolution.workspace.saveAndRefreshCandidates', '保存并更新候选') : t('courseEvolution.workspace.confirmScope', '确认影响范围') }}</button></footer>
              </section>
            </div>

            <div v-else-if="workspaceState === 'structure'" class="structure-layout">
              <section class="structure-review">
                <header class="review-header"><div><small>{{ t('courseEvolution.workspace.structureKicker', '结构变化') }}</small><h3>{{ t('courseEvolution.workspace.compareCourseTree', '先核对新旧课程树，再决定内容迁移') }}</h3></div><span><TriangleAlert :size="13" />{{ t('courseEvolution.workspace.structureFirst', '结构优先') }}</span></header>
                <div class="tree-comparison"><section><header><BookOpenText :size="16" /><b>{{ t('courseEvolution.workspace.currentTree', '当前课程树') }}</b></header><ol><li v-for="node in currentOutline" :key="node.node_id" :style="{ '--tree-level': Math.max(0, Number(node.node_level || 1) - 1) }"><span />{{ node.node_name }}</li></ol></section><ArrowRight :size="19" /><section class="proposed-tree structure-editor"><header><GitMerge :size="16" /><b>{{ t('courseEvolution.workspace.proposedTree', '调整后课程树') }}</b><button type="button" class="button-quiet compact-action" @click="resetOutlineDraft"><RotateCcw :size="13" />{{ t('courseEvolution.workspace.resetStructure', '恢复 AI 方案') }}</button></header><ol v-if="proposedOutline.length"><li v-for="(node, index) in proposedOutline" :key="node.provisional_id" :style="{ '--tree-level': treeLevel(node) }" class="structure-edit-row"><input v-model="node.title" :aria-label="t('courseEvolution.workspace.nodeTitle', '节点名称')" /><select v-model="node.parent_ref" :aria-label="t('courseEvolution.workspace.parentNode', '上级节点')"><option value="root">{{ t('courseEvolution.workspace.topLevel', '顶层') }}</option><option v-for="parent in proposedOutline.filter(item => !subtreeIds(node).has(item.provisional_id))" :key="parent.provisional_id" :value="parent.provisional_id">{{ parent.title }}</option></select><div><button type="button" :disabled="!siblingTarget(index, -1)" :title="t('courseEvolution.workspace.moveUp', '上移')" @click="moveOutlineNode(index, -1)"><ChevronUp :size="14" /></button><button type="button" :disabled="!siblingTarget(index, 1)" :title="t('courseEvolution.workspace.moveDown', '下移')" @click="moveOutlineNode(index, 1)"><ChevronDown :size="14" /></button><button type="button" :title="t('courseEvolution.workspace.splitNode', '拆分一个新节点')" @click="splitOutlineNode(index)"><CopyPlus :size="14" /></button><select class="merge-control" :aria-label="t('courseEvolution.workspace.mergeNode', '合并到其他节点')" @change="mergeOutlineNode(index, ($event.target as HTMLSelectElement))"><option value="">{{ t('courseEvolution.workspace.mergeInto', '合并到…') }}</option><option v-for="target in proposedOutline.filter(item => !subtreeIds(node).has(item.provisional_id))" :key="target.provisional_id" :value="target.provisional_id">{{ target.title }}</option></select><button type="button" :title="t('common.delete', '删除')" @click="removeOutlineNode(index)"><Trash2 :size="14" /></button></div></li></ol><p v-else>{{ t('courseEvolution.workspace.proposedTreePending', 'AI 已识别结构影响，但还需要你的补充才能形成可靠的新课程树。') }}</p><button type="button" class="button-secondary add-node" @click="addOutlineNode"><Plus :size="14" />{{ t('courseEvolution.workspace.addNode', '新增节点') }}</button></section></div>
                <details v-for="item in affectedUnits" :key="item.migration_id" class="source-preview"><summary>{{ item.title }} · {{ dispositionLabel(item.disposition) }}</summary><p v-if="item.candidate_error" class="candidate-error">{{ item.candidate_error }}</p><div v-if="item.after_content || item.after_preview" class="candidate-diff"><section><strong>{{ t('courseEvolution.workspace.beforeChange') }}</strong><p>{{ item.before_content || item.before_preview }}</p></section><section><strong>{{ t('courseEvolution.workspace.afterChange') }}</strong><p>{{ item.after_content || item.after_preview }}</p></section></div></details>
              </section>
              <aside class="migration-panel"><header><small>{{ t('courseEvolution.workspace.migrationKicker', '迁移判断') }}</small><strong>{{ t('courseEvolution.workspace.migrationTitle', '原内容如何处理') }}</strong></header><dl><div v-for="item in migrationSummary" :key="item.key"><dt>{{ item.label }}</dt><dd>{{ item.count }}</dd></div></dl><section v-if="migrationReviewItems.length"><header><TriangleAlert :size="15" /><b>{{ t('courseEvolution.workspace.needsReview', '需要老师判断') }}</b></header><ul><li v-for="item in migrationReviewItems.slice(0, 8)" :key="item.migration_id">{{ item.title }}: {{ item.reason }}</li></ul></section><p><ShieldCheck :size="15" />{{ structureConfirmed ? (candidateReviewReady ? t('courseEvolution.workspace.structureApplyHint', '结构与下游候选已就绪；应用时会保留逐资产回执和整次撤销。') : t('courseEvolution.workspace.structureGenerateHint', '结构已经锁定，正在原修改计划内生成下游候选。')) : t('courseEvolution.workspace.structureReviewHint', '先审阅具体的新结构和迁移方案，确认后再生成联动候选。') }}</p><div class="migration-actions"><button type="button" class="button-danger" :disabled="store.actingId === focusedPlan?.change_set_id" @click="discardPlan">{{ discardConfirm ? t('courseEvolution.workspace.confirmDiscard', '再次点击确认放弃') : t('courseEvolution.workspace.discardPlan', '放弃方案') }}</button><button v-if="structureConfirmed && candidateReviewReady" type="button" class="button-primary" :disabled="candidatesGenerating || store.actingId === focusedPlan?.change_set_id || structureApplicableCount === 0" @click="applyCourseChange"><LoaderCircle v-if="store.actingId === focusedPlan?.change_set_id" :size="15" class="spinning" /><Check v-else :size="15" />{{ structureApplicableCount ? applyStructureLabel : t('courseEvolution.workspace.structureCandidatePending', '等待稳定结构候选') }}</button><button v-else-if="structureConfirmed" type="button" class="button-primary" :disabled="store.actingId === focusedPlan?.change_set_id" @click="generateReviewedCandidates"><LoaderCircle v-if="store.actingId === focusedPlan?.change_set_id" :size="15" class="spinning" /><Sparkles v-else :size="15" />{{ t('courseEvolution.workspace.generateLinkedCandidates', '生成联动候选') }}</button><button v-else type="button" class="button-primary" :disabled="candidatesGenerating || store.actingId === focusedPlan?.change_set_id || !proposedOutline.length || !validOutlineDraft" @click="confirmStructure"><LoaderCircle v-if="store.actingId === focusedPlan?.change_set_id" :size="15" class="spinning" /><Check v-else :size="15" />{{ t('courseEvolution.workspace.confirmPlanAndGenerate', '确认方案并生成候选') }}</button></div></aside>
            </div>

            <main v-else class="receipt-state" :class="{ 'is-partial-undo': focusedPlan?.status === 'undo_partial' || applicationPartial }"><section><TriangleAlert v-if="focusedPlan?.status === 'undo_partial' || applicationPartial" :size="26" /><CircleCheckBig v-else :size="26" /><small>{{ receiptKicker }}</small><h3>{{ applicationTitle }}</h3><p>{{ rawRequest }}</p><dl><div><dt>{{ receiptPrimaryLabel }}</dt><dd>{{ receiptSummary.applied }}</dd></div><div><dt>{{ t('courseEvolution.workspace.failedItems', '失败') }}</dt><dd>{{ receiptSummary.failed }}</dd></div><div><dt>{{ t('courseEvolution.workspace.unchangedItems', '未变化') }}</dt><dd>{{ receiptSummary.unchanged }}</dd></div></dl><ul v-if="receiptItems.length" class="receipt-items"><li v-for="item in receiptItems" :key="item.migration_id || item.operation_id" :data-status="item.status"><span>{{ receiptStatusLabel(item.status) }}</span><b>{{ item.title || item.unit_id || assetLabel(item.domain || '') }}</b><small>{{ item.detail }}</small></li></ul><div class="receipt-actions"><button v-if="focusedPlan?.status === 'applied' && retryableFailedOperationIds.length" type="button" class="button-secondary" :disabled="store.actingId === focusedPlan?.change_set_id" @click="retryApplicationFailures"><RefreshCw :size="15" />{{ t('courseEvolution.workspace.retryFailedOnly', '只重试失败项') }}</button><button v-if="['applied', 'undo_partial'].includes(focusedPlan?.status || '')" type="button" class="button-secondary" :disabled="store.actingId === focusedPlan?.change_set_id" @click="undoCourseChange"><History :size="15" />{{ focusedPlan?.status === 'undo_partial' ? t('courseEvolution.workspace.retryUndo', '重试未完成的撤销') : t('courseEvolution.workspace.undoChange', '撤销本次修改') }}</button><button v-if="focusedPlan?.status !== 'undo_partial'" type="button" class="button-primary" @click="startNewRequest"><Sparkles :size="15" />{{ t('courseEvolution.workspace.newChange', '继续修改课程') }}</button></div></section></main>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, type Component } from 'vue'
import { ArrowLeft, ArrowRight, BookOpenText, BookText, BrainCircuit, Check, ChevronDown, ChevronUp, CircleCheckBig, ClipboardList, CopyPlus, FileQuestion, GitBranchPlus, GitMerge, History, LoaderCircle, PencilLine, Plus, Presentation, RefreshCw, RotateCcw, ScanSearch, ScrollText, Search, ShieldCheck, Sparkles, Trash2, TriangleAlert, X } from 'lucide-vue-next'
import { createUuid } from '../utils/client-id'
import { activeLocale, t } from '../shared/i18n'
import { useCourseEvolutionStore, observeCourseChangeProgress, type CourseEvolutionApplicationPresentation, type CourseEvolutionPlan, type TeacherCourseChangeContext, type TeacherCourseOutlineReviewNode, type TeacherMigrationDisposition } from '../stores/courseEvolution'

type WorkspaceState = 'request' | 'scanning' | 'interpreting' | 'content' | 'structure' | 'applied'
type ContextAsset = TeacherCourseChangeContext['assets'][number]
type AffectedUnit = { migration_id: string; unit_id: string; asset_type: string; unit_type: string; title: string; before_preview: string; before_content?: string; after_content?: string; after_preview?: string; section_ids: string[]; source_state: string; disposition: string; reason: string; confidence: number; candidate_status: string; candidate_error?: string; candidate_error_detail?: { retryable?: boolean }; operation_id?: string; change_count?: number }

const props = withDefaults(defineProps<{ modelValue: boolean; courseId: string; sectionId?: string; courseTitle?: string; sectionTitle?: string; focusPlanId?: string; standalone?: boolean; embeddedInCenter?: boolean }>(), { sectionId: '', courseTitle: '', sectionTitle: '', focusPlanId: '', standalone: false, embeddedInCenter: false })
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; courseApplied: [presentation: CourseEvolutionApplicationPresentation]; planSelected: [planId: string] }>()
const store = useCourseEvolutionStore()
const workspaceRef = ref<HTMLElement | null>(null)
const requestInputRef = ref<HTMLTextAreaElement | null>(null)
const previousFocus = ref<HTMLElement | null>(null)
const requestText = ref('')
const requestMode = ref<'describe' | 'replace' | 'structure'>('describe')
const findText = ref('')
const replacementText = ref('')
const requestAssetTypes = ref(['outline', 'lesson_plan', 'script', 'course_content'])
const requestCanSubmit = computed(() => requestMode.value === 'replace' ? Boolean(findText.value && findText.value !== replacementText.value && requestAssetTypes.value.length) : requestMode.value === 'structure' || Boolean(requestText.value.trim()))
const candidatesGenerating = computed(() => focusedPlan.value?.status === 'pending' && focusedPlan.value?.generation_status === 'generating')
const coverage = computed(() => focusedPlan.value?.impact_summary?.coverage)
const historyRef = ref<HTMLElement | null>(null)
const correctionText = ref('')
const correctionOpen = ref(false)
const actionError = ref('')
const selectedAsset = ref('')
const selectedPlanId = ref('')
const forceRequest = ref(false)
const excludedUnitIds = ref<Set<string>>(new Set())
const impactQuery = ref('')
const selectedSection = ref('')
const dispositionOverrides = ref<Record<string, TeacherMigrationDisposition>>({})
const outlineDraft = ref<TeacherCourseOutlineReviewNode[]>([])
const discardConfirm = ref(false)
const titleId = `course-change-${Math.random().toString(36).slice(2)}`

const context = computed(() => store.courseContext)
const courseLabel = computed(() => props.courseTitle || context.value?.course_title || t('courseEvolution.workspace.currentCourse', '当前课程'))
const focusedPlan = computed(() => {
  const preferredId = selectedPlanId.value || props.focusPlanId
  if (preferredId) {
    const preferred = store.plans.find(item => item.change_set_id === preferredId || item.plan_id === preferredId)
    if (preferred?.teacher_change_planning) return preferred
  }
  return [...store.plans].reverse().find(item => item.teacher_change_planning) || null
})
const planning = computed(() => focusedPlan.value?.teacher_change_planning || null)
const structuralPlan = computed(() => Boolean(
  planning.value?.structural_operations.length
  || planning.value?.execution_strategies.includes('structural_regeneration'),
))
const scopeAlreadyReviewed = computed(() => Boolean(focusedPlan.value?.impact_summary?.scope_review?.reviewed_at))
const standalone = computed(() => props.standalone)
const embeddedInCenter = computed(() => props.embeddedInCenter)
const hasApplicationReceipt = computed(() => Object.keys(focusedPlan.value?.application_receipt || {}).length > 0)
const hasUndoReceipt = computed(() => Object.keys(focusedPlan.value?.undo_receipt || {}).length > 0)
const workspaceState = computed<WorkspaceState>(() => {
  if (store.generating) return 'scanning'
  if (forceRequest.value || !focusedPlan.value || focusedPlan.value.status === 'rejected') return 'request'
  if (['applied', 'undo_partial', 'undone'].includes(focusedPlan.value.status) || hasApplicationReceipt.value || hasUndoReceipt.value) return 'applied'
  if (planning.value?.status === 'needs_clarification') return 'interpreting'
  if (structuralPlan.value && (scopeAlreadyReviewed.value || !focusedPlan.value?.impact_summary?.affected_units?.length || focusedPlan.value?.impact_summary?.analysis_mode === 'deterministic_structure')) return 'structure'
  return 'content'
})
const journeySteps = computed(() => [{ index: 1, label: t('courseEvolution.workspace.journeyRequest', '输入想法') }, { index: 2, label: t('courseEvolution.workspace.journeyAnalyze', '选择影响范围') }, { index: 3, label: t('courseEvolution.workspace.journeyReview', '审阅修改方案') }, { index: 4, label: t('courseEvolution.workspace.journeyApply', '确认应用') }])
const candidateOperationCount = computed(() => Number(focusedPlan.value?.impact_summary?.candidate_bundle?.operation_count || 0))
const hasGeneratedCandidates = computed(() => planning.value?.status === 'candidate_ready' && candidateOperationCount.value > 0)
const rawRequest = computed(() => planning.value?.intent.raw_request || focusedPlan.value?.request_text || '')
const interpretedGoal = computed(() => planning.value?.intent.interpreted_goal || focusedPlan.value?.expected_effect || rawRequest.value)
const protectedRequirements = computed(() => [...(planning.value?.intent.hard_constraints || []), ...(planning.value?.intent.protected_requirements || [])])
const contextUnavailable = computed(() => store.contextLoading || !context.value?.ready)
const contextAssets = computed(() => context.value?.assets || emptyAssets)
const availableContextAssets = computed(() => contextAssets.value.filter(item => item.state !== 'missing'))
const readyAssetCount = computed(() => availableContextAssets.value.length)
const contextStatusTitle = computed(() => store.contextLoading ? t('courseEvolution.workspace.indexLoading', '正在连接课程资产') : context.value?.ready ? t('courseEvolution.workspace.indexReady', '已连接真实课程资产') : t('courseEvolution.workspace.indexUnavailable', '尚无可分析内容'))
const affectedUnits = computed<AffectedUnit[]>(() => Array.isArray(focusedPlan.value?.impact_summary?.affected_units) ? focusedPlan.value?.impact_summary?.affected_units as AffectedUnit[] : [])
const affectedAssets = computed(() => { const counts = new Map<string, number>(); affectedUnits.value.forEach(item => counts.set(item.asset_type, (counts.get(item.asset_type) || 0) + 1)); return [...counts].map(([key, count]) => ({ key, count, label: assetLabel(key) })) })
const outlineLabelById = computed(() => new Map((context.value?.outline || []).map(item => [item.node_id, item.node_name])))
const affectedSections = computed(() => Array.from(new Set(affectedUnits.value.filter(item => item.asset_type === selectedAsset.value).flatMap(item => item.section_ids || []))).map(id => ({ id, label: outlineLabelById.value.get(id) || id })))
const visibleAffectedUnits = computed(() => {
  const query = impactQuery.value.trim().toLocaleLowerCase()
  return affectedUnits.value.filter(item => item.asset_type === selectedAsset.value && (!selectedSection.value || item.section_ids?.includes(selectedSection.value)) && (!query || [item.title, item.before_preview, item.reason].some(value => String(value || '').toLocaleLowerCase().includes(query))))
})
const selectedAssetLabel = computed(() => affectedAssets.value.find(item => item.key === selectedAsset.value)?.label || '')
const selectedImpactCount = computed(() => affectedUnits.value.length - excludedUnitIds.value.size)
const selectedApplicableOperationIds = computed(() => Array.from(new Set(affectedUnits.value.filter(item => !excludedUnitIds.value.has(item.migration_id) && item.operation_id && !['reuse_exact', 'reuse_rebind'].includes(effectiveDisposition(item))).map(item => String(item.operation_id)))))
const structureOperationIds = computed(() => (focusedPlan.value?.operations || []).filter(item => ['RESEQUENCE_COURSE_PATH', 'REBUILD_COURSE_OUTLINE'].includes(item.operation_type)).map(item => item.operation_id))
const selectedApplicableCount = computed(() => selectedApplicableOperationIds.value.length)
const structureApplicableCount = computed(() => new Set([...selectedApplicableOperationIds.value, ...structureOperationIds.value]).size)
const applySelectedLabel = computed(() => activeLocale.value === 'en' ? `Apply ${selectedApplicableCount.value} changes` : `应用 ${selectedApplicableCount.value} 项修改`)
const applyStructureLabel = computed(() => activeLocale.value === 'en' ? `Apply ${structureApplicableCount.value} linked changes` : `应用 ${structureApplicableCount.value} 项联动修改`)
const analysisMode = computed(() => String(focusedPlan.value?.impact_summary?.analysis_mode || 'index_fallback'))
const analysisModeLabel = computed(() => analysisMode.value === 'ai_ranked'
  ? t('courseEvolution.workspace.aiRanked', '索引召回后由 AI 判断')
  : analysisMode.value === 'deterministic_exact_replace'
    ? t('courseEvolution.workspace.exactReplaceValidated', '精确替换已校验')
    : t('courseEvolution.workspace.indexFallback', '当前为索引候选，需重点复核'))
const isIndexFallback = computed(() => analysisMode.value === 'index_fallback')
const impactUnitNoun = computed(() => isIndexFallback.value ? t('courseEvolution.workspace.candidateUnits', '个待复核候选') : t('courseEvolution.workspace.affectedUnits', '个受影响单元'))
const reviewImpactTitle = computed(() => isIndexFallback.value
  ? t('courseEvolution.workspace.reviewCandidates', '核对这些候选为什么被索引召回')
  : analysisMode.value === 'deterministic_exact_replace'
    ? t('courseEvolution.workspace.reviewExactReplace', '核对每一处精确替换')
    : t('courseEvolution.workspace.reviewImpact', '核对 AI 为什么认为这些内容会受影响'))
const scopeReview = computed(() => focusedPlan.value?.impact_summary?.scope_review || null)
const scopeSaved = computed(() => scopeAlreadyReviewed.value)
const savedSelectedMigrationIds = computed(() => new Set<string>(scopeSaved.value ? (scopeReview.value?.selected_migration_ids || []).map(String) : affectedUnits.value.map(item => item.migration_id)))
const selectionDirty = computed(() => affectedUnits.value.some(item => savedSelectedMigrationIds.value.has(item.migration_id) !== isUnitSelected(item.migration_id)))
const dispositionDirty = computed(() => affectedUnits.value.some(item => effectiveDisposition(item) !== item.disposition))
const reviewDirty = computed(() => selectionDirty.value || dispositionDirty.value)
const candidateReviewReady = computed(() => hasGeneratedCandidates.value && !reviewDirty.value)
const currentJourneyStep = computed(() => {
  if (workspaceState.value === 'content') return candidateReviewReady.value ? 4 : scopeSaved.value ? 3 : 2
  if (workspaceState.value === 'structure') return candidateReviewReady.value ? 4 : 3
  return ({ request: 1, scanning: 2, interpreting: 2, applied: 4 })[workspaceState.value]
})
const hasRetryableCandidateFailures = computed(() => affectedUnits.value.some(item => (item.candidate_status === 'failed' || Boolean(item.candidate_error)) && item.candidate_error_detail?.retryable !== false))
const hasNonRetryableCandidateFailures = computed(() => affectedUnits.value.some(item => item.candidate_status === 'failed' && item.candidate_error_detail?.retryable === false))
const changeKindLabel = computed(() => {
  const kind = planning.value?.execution_strategies.includes('structural_regeneration') ? t('courseEvolution.workspace.structureChange', '结构变化') : t('courseEvolution.workspace.contentChange', '内容变化')
  return planning.value?.supersedes_plan_id ? `${kind} · ${t('courseEvolution.workspace.revisedPlan', '修订版')}` : kind
})
const currentOutline = computed(() => Array.isArray(focusedPlan.value?.impact_summary?.current_outline) ? focusedPlan.value?.impact_summary?.current_outline : context.value?.outline || [])
const storedProposedOutline = computed<TeacherCourseOutlineReviewNode[]>(() => normalizeOutline(focusedPlan.value?.impact_summary?.proposed_outline))
const proposedOutline = computed(() => outlineDraft.value)
const structureDraftDirty = computed(() => JSON.stringify(outlineDraft.value) !== JSON.stringify(storedProposedOutline.value))
const validOutlineDraft = computed(() => validateOutlineDraft(outlineDraft.value))
const structureConfirmed = computed(() => planning.value?.structure_review_status === 'confirmed' && !structureDraftDirty.value)
const migrationSummary = computed(() => ([['reuse_exact', 'migrationReuse', '原样保留'], ['reuse_rebind', 'migrationRebind', '迁移重绑'], ['rewrite_partial', 'migrationRewrite', '局部改写'], ['regenerate', 'migrationRegenerate', '重新生成'], ['retire', 'migrationRetire', '停用'], ['blocked', 'migrationBlocked', '阻断']] as string[][]).map(([key, localeKey, fallback]) => ({ key, label: t(`courseEvolution.workspace.${localeKey}`, fallback), count: affectedUnits.value.filter(item => effectiveDisposition(item) === key).length })))
const migrationReviewItems = computed(() => affectedUnits.value.filter(item => ['blocked', 'regenerate', 'retire'].includes(effectiveDisposition(item))))
const recentPlans = computed(() => [...store.plans].reverse().filter(item => item.teacher_change_planning))
const domainUndoReceipt = computed(() => focusedPlan.value?.undo_receipt?.domain_candidates || null)
const showingUndoReceipt = computed(() => ['undo_partial', 'undone'].includes(focusedPlan.value?.status || ''))
const operationJournal = computed(() => Array.isArray(focusedPlan.value?.operation_journal)
  ? focusedPlan.value.operation_journal
  : [])
const retryableFailedOperationIds = computed(() => operationJournal.value
  .filter(item => item.status === 'failed' && item.retryable)
  .map(item => item.operation_id))
const applicationPartial = computed(() => focusedPlan.value?.application_receipt?.status === 'partial' || (focusedPlan.value?.operation_journal || []).some(item => item.status === 'failed'))
const applicationTitle = computed(() => focusedPlan.value?.status === 'undone'
  ? t('courseEvolution.workspace.undoneTitle', '本次修改已撤销')
  : focusedPlan.value?.status === 'undo_partial'
    ? t('courseEvolution.workspace.undoPartialTitle', '撤销尚未全部完成')
    : applicationPartial.value
      ? t('courseEvolution.workspace.partialTitle', '部分修改尚未完成')
      : t('courseEvolution.workspace.appliedTitle', '课程已按确认结果更新'))
const receiptKicker = computed(() => showingUndoReceipt.value ? t('courseEvolution.workspace.undoResult', '撤销结果') : applicationPartial.value ? t('courseEvolution.workspace.partialResult', '部分应用') : t('courseEvolution.workspace.appliedKicker', '应用完成'))
const receiptPrimaryLabel = computed(() => showingUndoReceipt.value ? t('courseEvolution.workspace.restoredItems', '已恢复') : t('courseEvolution.workspace.appliedItems', '已更新'))
const receiptSummary = computed(() => showingUndoReceipt.value && domainUndoReceipt.value
  ? { applied: Number(domainUndoReceipt.value.undone_count || 0), failed: Number(domainUndoReceipt.value.failed_count || 0), unchanged: 0 }
  : operationJournal.value.length
    ? {
        applied: operationJournal.value.filter(item => item.status === 'applied').length,
        failed: operationJournal.value.filter(item => item.status === 'failed').length,
        unchanged: Number(focusedPlan.value?.application_receipt?.unchanged_count ?? 0),
      }
    : { applied: Number(focusedPlan.value?.application_receipt?.applied_count ?? focusedPlan.value?.applied_block_ids?.length ?? 0), failed: Number(focusedPlan.value?.application_receipt?.failed_count ?? 0), unchanged: Number(focusedPlan.value?.application_receipt?.unchanged_count ?? 0) })
const receiptItems = computed<Array<{ migration_id?: string; operation_id?: string; unit_id?: string; title?: string; domain?: string; status: string; detail: string }>>(() => {
  if (showingUndoReceipt.value) {
    const values = domainUndoReceipt.value?.items
    return Array.isArray(values) ? values : []
  }
  if (operationJournal.value.length) {
    return operationJournal.value.map(item => ({
      operation_id: item.operation_id,
      unit_id: String(item.result_receipt?.unit_id || ''),
      title: String(item.result_receipt?.title || ''),
      domain: item.domain,
      status: item.status,
      detail: item.detail || String(item.result_receipt?.detail || ''),
    }))
  }
  const values = focusedPlan.value?.application_receipt?.items
  return Array.isArray(values) ? values : []
})
watch(() => [props.modelValue, props.courseId] as const, ([open, courseId], _, onCleanup) => { if (open && courseId) onCleanup(observeCourseChangeProgress(store, courseId)) }, { immediate: true })
const requestSuggestions = computed(() => [t('courseEvolution.workspace.suggestDetailedExamples', '所有案例都补充完整推导、反例和适用边界'), t('courseEvolution.workspace.suggestRestructure', '按新的教学逻辑重构章节，并迁移可以保留的内容'), t('courseEvolution.workspace.suggestVersionUpdate', '统一更新大纲、教案、讲义和 PPT 中过时的模型版本')])
const emptyAssets = (['outline', 'lesson_plan', 'script', 'ppt', 'question_bank'] as string[]).map(asset_type => ({ asset_type, label: asset_type, state: 'missing', count: 0, source: '', revision: '' })) as ContextAsset[]
const listSeparator = computed(() => activeLocale.value === 'en' ? '; ' : '；')

watch(affectedAssets, items => { if (!items.some(item => item.key === selectedAsset.value)) selectedAsset.value = items[0]?.key || '' }, { immediate: true })
watch(selectedAsset, () => { selectedSection.value = '' })
watch(() => focusedPlan.value?.change_set_id, () => {
  const saved = scopeReview.value?.excluded_migration_ids
  excludedUnitIds.value = new Set(Array.isArray(saved) ? saved.map(String) : [])
  dispositionOverrides.value = {}
  outlineDraft.value = normalizeOutline(focusedPlan.value?.impact_summary?.proposed_outline)
  impactQuery.value = ''
  selectedSection.value = ''
  discardConfirm.value = false
}, { immediate: true })
watch(() => props.modelValue, async open => { if (!open) return; previousFocus.value = document.activeElement instanceof HTMLElement ? document.activeElement : null; forceRequest.value = false; selectedPlanId.value = props.focusPlanId; await reloadWorkspace(); await nextTick(); workspaceRef.value?.focus(); if (workspaceState.value === 'request') requestInputRef.value?.focus() }, { immediate: true })
watch(() => props.focusPlanId, value => {
  if (!props.modelValue || !value) return
  selectedPlanId.value = value
  forceRequest.value = false
})

function assetIcon(value: string): Component { return ({ outline: BookText, course_content: BookOpenText, lesson_plan: ClipboardList, script: ScrollText, teacher_script: ScrollText, ppt: Presentation, slide_deck: Presentation, question_bank: FileQuestion } as Record<string, Component>)[value] || BookText }
function assetLabel(value: string) { const item = ({ outline: ['assetOutline', '课程大纲'], course_content: ['assetCourseContent', '课程正文'], lesson_plan: ['assetLessonPlan', '教案'], script: ['assetTeacherScript', '讲义'], teacher_script: ['assetTeacherScript', '讲义'], ppt: ['assetSlides', 'PPT'], slide_deck: ['assetSlides', 'PPT'], question_bank: ['assetQuestionBank', '题库'] } as Record<string, string[]>)[value]; return item ? t(`courseEvolution.workspace.${item[0]}`, item[1]) : value }
function assetStateLabel(value: ContextAsset['state']) { return ({ available: t('courseEvolution.workspace.assetAvailable', '可分析'), partial: t('courseEvolution.workspace.assetPartial', '部分完成'), missing: t('courseEvolution.workspace.assetMissing', '尚未生成'), stale: t('courseEvolution.workspace.assetStale', '需要同步') } as Record<string, string>)[value] }
function dispositionLabel(value: string) { const item = ({ reuse_exact: ['migrationReuse', '保留'], reuse_rebind: ['migrationRebind', '迁移重绑'], rewrite_partial: ['migrationRewrite', '局部改写'], regenerate: ['migrationRegenerate', '重新生成'], retire: ['migrationRetire', '停用'], blocked: ['migrationBlocked', '需判断'] } as Record<string, string[]>)[value]; return item ? t(`courseEvolution.workspace.${item[0]}`, item[1]) : value }
function effectiveDisposition(item: AffectedUnit) { return dispositionOverrides.value[item.migration_id] || item.disposition }
function dispositionOptions(item: AffectedUnit) {
  const values: TeacherMigrationDisposition[] = item.asset_type === 'question_bank'
    ? ['reuse_exact', 'reuse_rebind', 'rewrite_partial', 'regenerate', 'retire']
    : item.asset_type === 'outline' || item.asset_type === 'course_content'
      ? ['reuse_exact', 'reuse_rebind', 'rewrite_partial']
      : ['reuse_exact', 'reuse_rebind', 'rewrite_partial', 'regenerate']
  const options: Array<{ value: string; label: string }> = values.map(value => ({ value, label: dispositionLabel(value) }))
  if (effectiveDisposition(item) === 'blocked') options.unshift({ value: 'blocked', label: dispositionLabel('blocked') })
  return options
}
function setDisposition(item: AffectedUnit, value: string) {
  dispositionOverrides.value = { ...dispositionOverrides.value, [item.migration_id]: value as TeacherMigrationDisposition }
}
function confidenceLabel(value: number) { return value >= .8 ? t('courseEvolution.workspace.highConfidence', '高置信度') : value >= .6 ? t('courseEvolution.workspace.mediumConfidence', '中等置信度') : t('courseEvolution.workspace.lowConfidence', '需要重点复核') }
function receiptStatusLabel(value: string) { return ({ applied: t('courseEvolution.workspace.receiptApplied', '已更新'), undone: t('courseEvolution.workspace.receiptUndone', '已恢复'), failed: t('courseEvolution.workspace.receiptFailed', '失败'), unchanged: t('courseEvolution.workspace.receiptUnchanged', '未变化') } as Record<string, string>)[value] || value }
function treeLevel(node: Record<string, any>) {
  const byId = new Map(proposedOutline.value.map(item => [String(item.provisional_id), item]))
  const seen = new Set<string>()
  let parentId = String(node.parent_ref || node.parent_node_id || 'root')
  let level = 0
  while (parentId && parentId !== 'root' && !seen.has(parentId) && level < 6) {
    seen.add(parentId)
    level += 1
    const parent = byId.get(parentId)
    parentId = String(parent?.parent_ref || 'root')
  }
  return level
}
function normalizeOutline(value: unknown): TeacherCourseOutlineReviewNode[] {
  if (!Array.isArray(value)) return []
  return value.filter(item => item && typeof item === 'object').map((item: any, index) => ({
    provisional_id: String(item.provisional_id || item.node_id || `review-node-${index + 1}`),
    title: String(item.title || item.node_name || '').trim(),
    parent_ref: String(item.parent_ref || item.parent_node_id || 'root'),
    source_node_ids: Array.isArray(item.source_node_ids) ? item.source_node_ids.map(String) : (item.node_id ? [String(item.node_id)] : []),
    learning_focus: String(item.learning_focus || item.learning_objective || ''),
  }))
}
function validateOutlineDraft(nodes: TeacherCourseOutlineReviewNode[]) {
  if (!nodes.length || nodes.some(item => !item.provisional_id || !item.title.trim())) return false
  const ids = new Set(nodes.map(item => item.provisional_id))
  if (ids.size !== nodes.length || nodes.some(item => item.parent_ref !== 'root' && !ids.has(item.parent_ref))) return false
  return nodes.every(node => {
    const seen = new Set([node.provisional_id])
    let parent = node.parent_ref
    while (parent !== 'root') {
      if (seen.has(parent)) return false
      seen.add(parent)
      parent = nodes.find(item => item.provisional_id === parent)?.parent_ref || 'root'
    }
    return true
  })
}
function isUnitSelected(id: string) { return !excludedUnitIds.value.has(id) }
function toggleUnit(id: string) { const next = new Set(excludedUnitIds.value); if (next.has(id)) next.delete(id); else next.add(id); excludedUnitIds.value = next }
function selectVisibleUnits(include: boolean) { const next = new Set(excludedUnitIds.value); visibleAffectedUnits.value.forEach(item => include ? next.delete(item.migration_id) : next.add(item.migration_id)); excludedUnitIds.value = next }
function resetOutlineDraft() { outlineDraft.value = normalizeOutline(focusedPlan.value?.impact_summary?.proposed_outline) }
function subtreeIds(node: TeacherCourseOutlineReviewNode) {
  const ids = new Set([node.provisional_id])
  let changed = true
  while (changed) { changed = false; for (const item of outlineDraft.value) if (ids.has(item.parent_ref) && !ids.has(item.provisional_id)) { ids.add(item.provisional_id); changed = true } }
  return ids
}
function siblingTarget(index: number, direction: -1 | 1) {
  const node = outlineDraft.value[index]
  if (!node) return undefined
  const siblings = outlineDraft.value.filter(item => item.parent_ref === node.parent_ref)
  return siblings[siblings.indexOf(node) + direction]
}
function moveOutlineNode(index: number, direction: -1 | 1) {
  const node = outlineDraft.value[index], target = siblingTarget(index, direction)
  if (!node || !target) return
  const ownIds = subtreeIds(node), targetIds = subtreeIds(target)
  const own = outlineDraft.value.filter(item => ownIds.has(item.provisional_id))
  const remaining = outlineDraft.value.filter(item => !ownIds.has(item.provisional_id))
  const position = direction < 0 ? remaining.indexOf(target) : Math.max(...remaining.map((item, i) => targetIds.has(item.provisional_id) ? i : -1)) + 1
  remaining.splice(position, 0, ...own)
  outlineDraft.value = remaining
}
function addOutlineNode() { outlineDraft.value = [...outlineDraft.value, { provisional_id: `teacher-node-${Date.now()}`, title: t('courseEvolution.workspace.newNodeTitle', '新节点'), parent_ref: 'root', source_node_ids: [], learning_focus: '' }] }
function splitOutlineNode(index: number) { const source = outlineDraft.value[index]; if (!source) return; const next = [...outlineDraft.value]; next.splice(index + 1, 0, { provisional_id: `teacher-node-${Date.now()}`, title: `${source.title}${t('courseEvolution.workspace.splitSuffix', '（拆分）')}`, parent_ref: source.parent_ref, source_node_ids: [], learning_focus: source.learning_focus || '' }); outlineDraft.value = next }
function removeOutlineNode(index: number) { const removed = outlineDraft.value[index]; if (!removed) return; const ids = subtreeIds(removed); outlineDraft.value = outlineDraft.value.filter(item => !ids.has(item.provisional_id)) }
function mergeOutlineNode(index: number, control: HTMLSelectElement) { const targetId = control.value; control.value = ''; const source = outlineDraft.value[index]; const target = outlineDraft.value.find(item => item.provisional_id === targetId); if (!source || !target) return; target.source_node_ids = Array.from(new Set([...target.source_node_ids, ...source.source_node_ids])); outlineDraft.value = outlineDraft.value.filter((_, itemIndex) => itemIndex !== index).map(item => item.parent_ref === source.provisional_id ? { ...item, parent_ref: target.provisional_id } : item) }
function recentPlanStatus(plan: CourseEvolutionPlan) { if (plan.status === 'applied') return t('courseEvolution.workspace.recentApplied', '已应用'); if (plan.status === 'undo_partial') return t('courseEvolution.workspace.recentUndoPartial', '撤销未完成'); if (plan.status === 'undone') return t('courseEvolution.workspace.recentUndone', '已撤销'); if (plan.impact_summary?.superseded_by_plan_id) return t('courseEvolution.workspace.supersededPlan', '已被修订'); if (plan.status === 'rejected') return t('courseEvolution.workspace.recentRejected', '已放弃'); return plan.impact_summary?.scope_review?.reviewed_at ? t('courseEvolution.workspace.recentReviewed', '已审阅') : t('courseEvolution.workspace.recentPending', '待审阅') }
function formatPlanTime(plan: CourseEvolutionPlan) { const value = plan.teacher_change_planning?.updated_at || plan.teacher_change_planning?.created_at; if (!value) return ''; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(activeLocale.value === 'en' ? 'en-US' : 'zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date) }
function readableError(error: any, fallback: string) { if (Number(error?.response?.status) === 404) return t('courseEvolution.workspace.courseMissing', '未找到当前课程，请返回课程列表重新进入。'); return String(error?.response?.data?.detail?.message || error?.response?.data?.detail || error?.message || fallback) }
async function reloadWorkspace() { actionError.value = ''; try { await Promise.all([store.refreshProgress(props.courseId), store.loadCourseContext(props.courseId)]) } catch (error: any) { actionError.value = readableError(error, '课程资产读取失败，请重试。') } }
async function submitRequest() {
  if (!requestCanSubmit.value || contextUnavailable.value) return
  actionError.value = ''; forceRequest.value = false
  const requestId = createUuid()
  const courseId = props.courseId
  const instruction = requestMode.value === 'replace' ? t('courseEvolution.workspace.replaceInstruction').replace('{before}', findText.value).replace('{after}', replacementText.value) : requestMode.value === 'structure' ? '编辑讲次结构' : requestText.value.trim()
  try {
    const result = await store.createCoursePlan({ courseId, requestId, instruction, assetTypes: requestMode.value === 'replace' ? requestAssetTypes.value : ['outline', 'lesson_plan', 'script', 'course_content', 'question_bank'], ...(requestMode.value === 'replace' ? { literalReplacement: { before: findText.value, after: replacementText.value } } : {}) })
    if (props.courseId === courseId) selectCreatedPlan(result, requestId)
  } catch (error: any) { if (props.courseId === courseId) { actionError.value = readableError(error, t('courseEvolution.workspace.analysisFailed')); forceRequest.value = true } }
}
function selectCreatedPlan(payload: Record<string, any>, requestId = '') {
  const plans: CourseEvolutionPlan[] = payload.course_evolution_plans || payload.change_sets || store.plans
  const created = plans.find(item => requestId && item.impact_summary?.request_id === requestId) || [...plans].reverse().find(item => item.teacher_change_planning && item.status === 'pending')
  if (created) { selectedPlanId.value = created.change_set_id; emit('planSelected', created.change_set_id) }
}
function openCorrection() { correctionText.value = ''; correctionOpen.value = true }
async function submitCorrection() { if (!correctionText.value.trim() || !focusedPlan.value) return; const requestId = createUuid(); const courseId = props.courseId; const combined = `${rawRequest.value}\n补充修正：${correctionText.value.trim()}`.trim(); actionError.value = ''; try { const result = await store.createCoursePlan({ courseId, requestId, instruction: combined, supersedesPlanId: focusedPlan.value.change_set_id, assetTypes: ['outline', 'lesson_plan', 'script', 'course_content', 'question_bank'] }); if (props.courseId === courseId) { correctionOpen.value = false; selectCreatedPlan(result, requestId) } } catch (error: any) { actionError.value = String(error?.response?.data?.detail?.message || error?.message || '重新分析失败，请重试。') } }
function reviewedMigrationIds() { return affectedUnits.value.filter(item => !excludedUnitIds.value.has(item.migration_id)).map(item => item.migration_id) }
function reviewedDispositions() { return Object.fromEntries(affectedUnits.value.map(item => [item.migration_id, effectiveDisposition(item)]).filter(([, disposition]) => disposition !== 'blocked')) as Record<string, TeacherMigrationDisposition> }
async function saveScopeReview() { if (!focusedPlan.value) return; actionError.value = ''; const planId = focusedPlan.value.change_set_id; try { await store.reviewCoursePlan(planId, reviewedMigrationIds(), { migrationDispositions: reviewedDispositions() }); if (!structuralPlan.value) await store.generateSuggested(planId) } catch (error: any) { actionError.value = String(error?.response?.data?.detail?.message || error?.message || '影响范围确认或候选生成失败，请重试。') } }
async function confirmStructure() { if (!focusedPlan.value || !proposedOutline.value.length || !validOutlineDraft.value) return; actionError.value = ''; const planId = focusedPlan.value.change_set_id; try { await store.reviewCoursePlan(planId, reviewedMigrationIds(), { confirmStructure: true, migrationDispositions: reviewedDispositions(), proposedOutline: normalizeOutline(proposedOutline.value) }); await store.generateSuggested(planId) } catch (error: any) { actionError.value = String(error?.response?.data?.detail?.message || error?.message || '结构确认或联动候选生成失败，请重试。') } }
async function generateReviewedCandidates() { if (!focusedPlan.value) return; actionError.value = ''; try { await store.generateSuggested(focusedPlan.value.change_set_id) } catch (error: any) { actionError.value = String(error?.response?.data?.detail?.message || error?.message || '联动候选生成失败，请重试。') } }
async function retryCandidateFailures() { if (!focusedPlan.value) return; actionError.value = ''; try { await store.generateSuggested(focusedPlan.value.change_set_id) } catch (error: any) { actionError.value = String(error?.response?.data?.detail?.message || error?.message || '失败项重试失败，已保留其他成功候选。') } }
async function applyCourseChange() { if (!focusedPlan.value) return; const operationIds = Array.from(new Set([...selectedApplicableOperationIds.value, ...(structureConfirmed.value ? structureOperationIds.value : [])])); if (!operationIds.length) return; actionError.value = ''; try { await store.accept(focusedPlan.value.change_set_id, 'current', operationIds); const applied = store.plans.find(item => item.change_set_id === focusedPlan.value?.change_set_id); const firstOperation = applied?.operations.find(item => operationIds.includes(item.operation_id)); emit('courseApplied', { planId: applied?.change_set_id || focusedPlan.value.change_set_id, affectedSectionIds: Array.from(new Set((applied?.operations || []).filter(item => operationIds.includes(item.operation_id)).map(item => item.target_section_id).filter(Boolean))), appliedBlockIds: applied?.applied_block_ids || [], operationIds, targetSectionId: firstOperation?.target_section_id || '', targetBlockId: firstOperation?.target_block_id || '', targetOperationId: firstOperation?.operation_id || '' }) } catch (error: any) { actionError.value = String(error?.response?.data?.detail?.message || error?.message || '应用课程修改失败，请重试。') } }
async function undoCourseChange() { if (!focusedPlan.value) return; actionError.value = ''; try { await store.undo(focusedPlan.value.change_set_id) } catch (error: any) { actionError.value = String(error?.response?.data?.detail?.message || error?.message || '撤销失败，请重试。') } }
async function retryApplicationFailures() { if (!focusedPlan.value || !retryableFailedOperationIds.value.length) return; actionError.value = ''; try { await store.accept(focusedPlan.value.change_set_id, focusedPlan.value.selected_scope || 'current', retryableFailedOperationIds.value, { retryFailed: true }) } catch (error: any) { actionError.value = String(error?.response?.data?.detail?.message || error?.message || '失败资产重试失败，已成功项未重复执行。') } }
async function discardPlan() { if (!focusedPlan.value) return; if (!discardConfirm.value) { discardConfirm.value = true; return } actionError.value = ''; try { await store.reject(focusedPlan.value.change_set_id, '教师在审阅工作区主动放弃方案'); discardConfirm.value = false; startNewRequest() } catch (error: any) { actionError.value = String(error?.response?.data?.detail?.message || error?.message || '放弃方案失败，请重试。') } }
function startNewRequest() { forceRequest.value = true; selectedPlanId.value = ''; requestText.value = ''; correctionOpen.value = false; actionError.value = ''; store.generationError = ''; nextTick(() => requestInputRef.value?.focus()) }
function openPlan(id: string) { selectedPlanId.value = id; forceRequest.value = false }
function close() { emit('update:modelValue', false); nextTick(() => previousFocus.value?.focus()) }
function handleKeydown(event: KeyboardEvent) { if (event.key === 'Escape') { event.preventDefault(); close(); return } if (standalone.value || event.key !== 'Tab' || !workspaceRef.value) return; const focusable = [...workspaceRef.value.querySelectorAll<HTMLElement>('button:not([disabled]), textarea:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])')].filter(item => !item.hasAttribute('hidden')); if (!focusable.length) { event.preventDefault(); workspaceRef.value.focus(); return } const first = focusable[0]!; const last = focusable[focusable.length - 1]!; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() } }
function showHistory() { forceRequest.value = true; nextTick(() => historyRef.value?.scrollIntoView({ block: 'start' })) }
defineExpose({ reloadWorkspace, openPlan, startNewRequest, showHistory })
</script>

<style scoped>
.course-change-layer{position:fixed;inset:0;z-index:1200;display:grid;place-items:center;padding:24px}.course-change-backdrop{position:absolute;inset:0;width:100%;height:100%;border:0;background:rgba(15,23,42,.52);backdrop-filter:blur(3px)}.course-change-workspace{position:relative;width:min(1320px,calc(100vw - 48px));height:min(880px,calc(100dvh - 48px));display:grid;grid-template-rows:68px 58px auto minmax(0,1fr);overflow:hidden;border-radius:16px;color:#344054;background:#f5f7fb;box-shadow:0 28px 78px rgba(15,23,42,.28);outline:0}.workspace-header{display:grid;grid-template-columns:40px minmax(210px,1fr) minmax(180px,auto) 38px 38px;align-items:center;gap:11px;padding:0 18px 0 20px;border-bottom:1px solid #e3e7ef;background:#fff}.workspace-mark{width:40px;height:40px;display:grid;place-items:center;border-radius:12px;color:#fff;background:#5b54e8;box-shadow:0 8px 18px rgba(63,56,187,.22)}.workspace-title small{display:block;color:#667085;font-size:10px;font-weight:700}.workspace-title h2{margin:2px 0 0;color:#172033;font-size:18px;letter-spacing:-.02em}.course-identity{min-width:0;max-width:310px;display:flex;align-items:center;justify-self:end;gap:7px;padding:8px 10px;border-radius:9px;color:#596579;background:#f3f5f8;font-size:12px}.course-identity svg{flex:none;color:#5b54e8}.course-identity span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.icon-action{width:38px;height:38px;display:grid;place-items:center;border:0;border-radius:9px;color:#667085;background:transparent;cursor:pointer}.icon-action:hover:not(:disabled){color:#4e46d4;background:#f0efff}.icon-action:disabled{opacity:.45}.icon-action:focus-visible,.request-suggestions button:focus-visible,.request-context button:focus-visible{outline:3px solid rgba(91,84,232,.22);outline-offset:1px}.journey{position:relative;z-index:2;padding:13px clamp(36px,7vw,96px);border-bottom:1px solid #e3e7ef;background:#fff}.journey ol{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:0;padding:0;list-style:none}.journey li{position:relative;display:grid;grid-template-columns:28px minmax(0,1fr);align-items:center;gap:9px;color:#667085;font-size:11px}.journey li::after{position:absolute;z-index:-1;top:14px;left:calc(50% + 22px);right:calc(-50% + 22px);height:1px;background:#dfe4ec;content:""}.journey li:last-child::after{display:none}.journey li>span{width:28px;height:28px;display:grid;place-items:center;border:1px solid #98a2b3;border-radius:50%;color:#596579;background:#fff;font-size:10px;font-weight:800}.journey li>b{font-weight:700}.journey li.complete,.journey li.active{color:#4d46cc}.journey li.complete::after{background:#9c97ec}.journey li.complete>span{border-color:#716ae7;color:#fff;background:#716ae7}.journey li.active>span{border:2px solid #5b54e8;color:#4038bb;background:#efeeff;box-shadow:0 0 0 3px #e8e7ff}.request-context{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.2fr) auto;align-items:center;padding:9px 20px;border-bottom:1px solid #deddf6;background:#f8f7ff}.request-context>div{min-width:0;padding:0 14px;border-right:1px solid #deddf6}.request-context>div:first-child{padding-left:0}.request-context small{display:block;margin-bottom:2px;color:#5f58bd;font-size:9px;font-weight:750}.request-context p{overflow:hidden;margin:0;color:#3d4656;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.request-context button{display:inline-flex;align-items:center;gap:6px;margin-left:12px;padding:8px 9px;border:0;border-radius:8px;color:#5148dc;background:transparent;font-size:11px;font-weight:750;cursor:pointer}.request-context button:hover{background:#ecebff}.correction-bar{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:12px;padding:12px 20px;border-bottom:1px solid #d8d7fa;background:#f8f7ff}.correction-bar label{display:grid;gap:6px;color:#353d4d;font-size:11px;font-weight:700}.correction-bar textarea{width:100%;padding:9px 11px;border:1px solid #aeb7c5;border-radius:9px;color:#172033;background:#fff;font:inherit;line-height:1.5;resize:vertical;box-sizing:border-box}.correction-bar>div{display:flex;gap:7px}.workspace-stage{min-height:0;overflow:auto}.request-state{width:min(1120px,calc(100% - 44px));min-height:100%;display:grid;grid-template-columns:minmax(0,1.7fr) minmax(280px,.78fr);align-content:start;gap:22px;margin:0 auto;padding:28px 0 40px;box-sizing:border-box}.request-composer,.asset-ledger{border-radius:15px;background:#fff;box-shadow:0 12px 32px rgba(20,29,49,.07)}.request-composer{padding:26px 28px}.request-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:18px}.request-heading span,.asset-ledger header span,.scan-heading small,.review-header small,.impact-nav>header small,.migration-panel>header small,.clarification-heading small,.receipt-state small{color:#5148dc;font-size:10px;font-weight:800}.request-heading h3{margin:5px 0 0;color:#172033;font-size:23px;letter-spacing:-.025em}.request-heading>small{max-width:220px;color:#596579;font-size:11px;line-height:1.5;text-align:right}.request-composer form>textarea{width:100%;min-height:142px;padding:16px 17px;border:1px solid #aeb7c5;border-radius:12px;color:#172033;background:#fff;font:500 14px/1.7 inherit;resize:vertical;box-sizing:border-box}.request-composer form>textarea::placeholder{color:#667085}.request-composer form>textarea:focus{border-color:#746de5;outline:3px solid rgba(91,84,232,.14)}.request-suggestions{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}.request-suggestions button{padding:7px 9px;border:1px solid #d5dae3;border-radius:8px;color:#4a5568;background:#f7f8fa;font-size:10px;cursor:pointer}.request-suggestions button:hover{border-color:#c7c4f8;color:#4f47d0;background:#f3f2ff}.request-composer form>footer{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:18px}.request-composer form>footer>span{display:flex;align-items:center;gap:6px;color:#4f5d70;font-size:11px}.request-composer form>footer>span svg{color:#087354}.button-primary,.button-secondary,.button-quiet{min-height:38px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 14px;border-radius:9px;font-size:12px;font-weight:750;cursor:pointer}.button-primary{border:1px solid #5148dc;color:#fff;background:#5148dc;box-shadow:0 6px 14px rgba(81,72,220,.18)}.button-primary:hover:not(:disabled){background:#433bc4}.button-primary:disabled{opacity:.45;cursor:not-allowed;box-shadow:none}.button-secondary{border:1px solid #cfd5df;color:#3d4656;background:#fff}.button-secondary:hover{border-color:#c8c5f7;color:#4e46ce;background:#f8f7ff}.button-quiet{border:0;color:#5148dc;background:transparent}.button-submit{min-height:43px;padding:0 18px}.inline-error{display:flex;align-items:center;gap:7px;margin:12px 0 0;color:#b42318;font-size:11px}.recent-changes{margin-top:24px;padding-top:18px;border-top:1px solid #e0e4eb}.recent-changes>header{display:flex;align-items:center;gap:7px;color:#344054;font-size:12px}.recent-changes ol{display:grid;gap:6px;margin:11px 0 0;padding:0;list-style:none}.recent-changes li{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:9px}.recent-changes li>span{padding:4px 6px;border-radius:6px;color:#5148dc;background:#efeeff;font-size:9px;font-weight:750}.recent-changes li>span[data-status=applied]{color:#087354;background:#eaf8f2}.recent-changes li>button{min-width:0;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:5px 0;border:0;color:#344054;background:transparent;text-align:left;cursor:pointer}.recent-changes li b{overflow:hidden;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.recent-changes li small{flex:none;color:#667085;font-size:9px}.recent-changes>p{margin:11px 0 0;color:#667085;font-size:11px}.asset-ledger{align-self:start;padding:22px}.asset-ledger>header{display:flex;align-items:center;justify-content:space-between;color:#087354}.asset-ledger>header div{display:grid;gap:4px}.asset-ledger>header strong{color:#172033;font-size:14px}.asset-ledger>p{margin:9px 0 16px;color:#596579;font-size:10px;line-height:1.5}.asset-ledger ul{display:grid;gap:2px;margin:0;padding:0;list-style:none}.asset-ledger li{display:grid;grid-template-columns:22px minmax(0,1fr) auto;align-items:center;gap:8px;padding:10px 8px;border-bottom:1px solid #e3e7ee;color:#596579}.asset-ledger li:last-child{border-bottom:0}.asset-ledger li>svg{color:#5f58c7}.asset-ledger li div{display:grid;gap:2px}.asset-ledger li b{color:#344054;font-size:11px}.asset-ledger li small{color:#596579;font-size:9px}.asset-ledger li strong{color:#172033;font-size:13px}.asset-ledger>footer{display:flex;gap:12px;margin-top:14px;padding-top:13px;border-top:1px solid #e0e4eb;color:#4f5d70;font-size:9px}.scanning-state{width:min(980px,calc(100% - 44px));min-height:100%;display:grid;grid-template-columns:minmax(0,1.7fr) minmax(240px,.7fr);align-content:center;gap:20px;margin:auto;padding:28px 0;box-sizing:border-box}.scan-main,.scanning-state>aside,.clarification-state>section,.receipt-state>section{border-radius:15px;background:#fff;box-shadow:0 14px 38px rgba(20,29,49,.08)}.scan-main{display:grid;gap:24px;padding:34px}.scan-heading{display:grid;grid-template-columns:44px minmax(0,1fr);align-items:center;gap:13px}.scan-heading>span{width:44px;height:44px;display:grid;place-items:center;border-radius:12px;color:#5148dc;background:#efeeff}.scan-heading h3{margin:4px 0 0;color:#172033;font-size:19px}.scan-line{height:4px;overflow:hidden;border-radius:4px;background:#dfe3ea}.scan-line span{width:30%;height:100%;display:block;border-radius:4px;background:#5b54e8;animation:scan-sweep 1.4s cubic-bezier(.16,1,.3,1) infinite}.scan-main dl{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin:0;background:#dfe3ea}.scan-main dl div{padding:13px;background:#f8f9fb}.scan-main dt{color:#596579;font-size:9px}.scan-main dd{margin:4px 0 0;color:#344054;font-size:11px;font-weight:700}.scan-main>p{display:flex;align-items:center;gap:7px;margin:0;color:#087354;font-size:11px}.scanning-state>aside{padding:24px}.scanning-state>aside header{margin-bottom:13px;color:#344054;font-size:11px;font-weight:750}.scanning-state>aside ul{display:grid;gap:5px;margin:0;padding:0;list-style:none}.scanning-state>aside li{display:grid;grid-template-columns:20px minmax(0,1fr) 16px;align-items:center;gap:7px;padding:9px 10px;border-radius:8px;color:#4a5568;background:#f6f7fa;font-size:11px;animation:scan-item .38s cubic-bezier(.16,1,.3,1) both;animation-delay:var(--scan-delay)}.scanning-state>aside li svg:last-child{color:#087354}.clarification-state,.receipt-state{min-height:100%;display:grid;place-items:center;padding:32px}.clarification-state>section,.receipt-state>section{width:min(680px,100%);padding:32px;box-sizing:border-box}.clarification-heading{display:grid;grid-template-columns:34px minmax(0,1fr);gap:11px;color:#5148dc}.clarification-heading h3{margin:4px 0 0;color:#172033;font-size:18px;line-height:1.45}.clarification-state>section>p{color:#596579;font-size:12px}.clarification-state ol{display:grid;gap:8px;margin:18px 0;padding:0;list-style:none;counter-reset:question}.clarification-state li{padding:12px 14px;border-radius:9px;color:#6d4c15;background:#fff7e7;font-size:12px;counter-increment:question}.clarification-state li::before{margin-right:7px;font-weight:800;content:counter(question) "."}.review-layout{min-height:100%;display:grid;grid-template-columns:232px minmax(0,1fr)}.impact-nav{min-height:0;overflow:auto;padding:24px 18px;border-right:1px solid #e2e6ed;background:#fff}.impact-nav>header{display:grid;gap:5px;margin-bottom:17px}.impact-nav>header strong{color:#172033;font-size:15px}.impact-nav>header p{margin:0;color:#596579;font-size:10px;line-height:1.5}.impact-nav nav{display:grid;gap:5px}.impact-nav nav button{display:grid;grid-template-columns:18px minmax(0,1fr) auto;align-items:center;gap:8px;min-height:42px;padding:0 10px;border:1px solid transparent;border-radius:9px;color:#4a5568;background:#f6f7fa;font-size:11px;text-align:left;cursor:pointer}.impact-nav nav button.active{border-color:#cbc8fa;color:#4e46cf;background:#f0efff}.protected-scope{display:grid;grid-template-columns:18px minmax(0,1fr);gap:8px;margin-top:18px;padding:11px;border-radius:9px;color:#087354;background:#edf8f4}.protected-scope b{font-size:10px}.protected-scope p{margin:4px 0 0;font-size:9px;line-height:1.5}.scope-counts{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:18px 0 0}.scope-counts div{padding:10px;border-radius:8px;background:#f6f7fa}.scope-counts dt{color:#596579;font-size:9px}.scope-counts dd{margin:4px 0 0;color:#172033;font-size:17px;font-weight:800}.impact-review{min-width:0;min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr) auto;overflow:hidden;padding:22px 28px 0}.review-header{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;padding-bottom:16px}.review-header h3{margin:4px 0 0;color:#172033;font-size:17px;letter-spacing:-.015em}.review-header>span{display:inline-flex;align-items:center;gap:5px;padding:6px 8px;border-radius:7px;color:#087354;background:#eaf8f2;font-size:9px;font-weight:750}.impact-list{display:grid;align-content:start;gap:9px;overflow:auto;padding:0 2px 24px}.impact-list article{display:grid;grid-template-columns:28px minmax(0,1fr);gap:7px;padding:15px 16px 14px 11px;border:1px solid #d8dde6;border-radius:13px;background:#fff;transition:border-color .18s ease,opacity .18s ease}.impact-list article:hover{border-color:#b8b3ef}.impact-list article.excluded{opacity:.5}.impact-check{position:relative;padding-top:2px;cursor:pointer}.impact-check input{position:absolute;opacity:0}.impact-check span{width:17px;height:17px;display:grid;place-items:center;border:1px solid #98a2b3;border-radius:5px;background:#fff}.impact-check input:checked+span{border-color:#5b54e8;background:#5b54e8}.impact-check input:checked+span::after{width:7px;height:4px;border:solid #fff;border-width:0 0 2px 2px;transform:rotate(-45deg) translateY(-1px);content:""}.impact-check input:focus-visible+span{outline:3px solid rgba(91,84,232,.2);outline-offset:2px}.impact-copy>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.impact-copy>header small{color:#596579;font-size:9px}.impact-copy h4{margin:3px 0 0;color:#172033;font-size:13px}.impact-copy>header>span{flex:none;padding:4px 7px;border-radius:6px;color:#5148dc;background:#efeeff;font-size:9px;font-weight:750}.impact-copy>header>span[data-disposition=regenerate],.impact-copy>header>span[data-disposition=retire],.impact-copy>header>span[data-disposition=blocked]{color:#784d0b;background:#fff5df}.impact-reason{margin:7px 0 10px;color:#4a5568;font-size:11px;line-height:1.55}.source-preview{padding:10px 11px;border-radius:9px;background:#f6f7fa}.source-preview small{color:#596579;font-size:9px;font-weight:700}.source-preview p{display:-webkit-box;overflow:hidden;margin:4px 0 0;color:#3d4656;font-size:10px;line-height:1.6;-webkit-box-orient:vertical;-webkit-line-clamp:3}.impact-copy>footer{display:flex;justify-content:space-between;gap:8px;margin-top:8px;color:#596579;font-size:9px}.impact-copy>footer span{display:inline-flex;align-items:center;gap:4px}.impact-copy>footer span:first-child{color:#8b5205}.empty-impact{display:grid;place-items:center;min-height:180px;margin:0;color:#596579;font-size:11px}.review-actionbar{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:9px;margin:0 -28px;padding:12px 20px;border-top:1px solid #dce1e9;background:#fff}.review-actionbar>div strong{display:flex;align-items:center;gap:6px;color:#087354;font-size:11px}.review-actionbar>div p{margin:2px 0 0;color:#4f5d70;font-size:9px}.structure-layout{min-height:100%;display:grid;grid-template-columns:minmax(0,1fr) 286px}.structure-review{min-width:0;display:flex;flex-direction:column;gap:8px;overflow:auto;padding:24px 28px 38px}.tree-comparison{display:grid;grid-template-columns:minmax(0,1fr) 20px minmax(0,1fr);align-items:start;gap:12px}.tree-comparison>svg{margin-top:22px;color:#596579}.tree-comparison>section{min-width:0;padding:15px;border:1px solid #d6dbe4;border-radius:13px;background:#fff}.tree-comparison>section.proposed-tree{border-color:#bdb8ef;background:#fbfaff}.tree-comparison section>header{display:flex;align-items:center;gap:7px;color:#344054;font-size:11px}.tree-comparison ol{display:grid;gap:5px;margin:13px 0 0;padding:0;list-style:none}.tree-comparison li{display:grid;grid-template-columns:9px minmax(0,1fr);align-items:center;gap:7px;margin-left:calc(var(--tree-level) * 14px);padding:7px 8px;border-radius:7px;color:#4a5568;background:#f6f7fa;font-size:10px}.tree-comparison li span{width:6px;height:6px;border:2px solid #7b8494;border-radius:50%}.proposed-tree li{color:#4d46c8;background:#efeeff}.proposed-tree li span{border-color:#655ee0}.proposed-tree>p{margin:14px 0 0;padding:14px;border-radius:9px;color:#6d4c15;background:#fff6e6;font-size:11px;line-height:1.6}.migration-panel{padding:24px 20px;border-left:1px solid #e1e5ec;background:#fff}.migration-panel>header{display:grid;gap:4px}.migration-panel>header strong{color:#172033;font-size:14px}.migration-panel>dl{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:17px 0}.migration-panel>dl div{padding:10px;border-radius:8px;background:#f6f7fa}.migration-panel dt{color:#596579;font-size:9px}.migration-panel dd{margin:3px 0 0;color:#172033;font-size:17px;font-weight:800}.migration-panel>section{padding:11px;border-radius:9px;color:#6d4c15;background:#fff6e6}.migration-panel>section header{display:flex;align-items:center;gap:6px;font-size:10px}.migration-panel>section ul{margin:8px 0 0;padding-left:15px;font-size:9px;line-height:1.55}.migration-panel>p{display:flex;align-items:flex-start;gap:6px;margin:16px 0;color:#4f5d70;font-size:10px;line-height:1.5}.migration-panel>.button-primary{width:100%}.receipt-state>section{text-align:center}.receipt-state>section>svg{color:#087354}.receipt-state h3{margin:6px 0;color:#172033;font-size:20px}.receipt-state>section>p{color:#4f5d70;font-size:11px}.receipt-state dl{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:20px 0}.receipt-state dl div{padding:12px;border-radius:9px;background:#f6f7fa}.receipt-state dt{color:#596579;font-size:9px}.receipt-state dd{margin:4px 0 0;color:#172033;font-size:20px;font-weight:800}.spinning{animation:spin .8s linear infinite}.course-change-layer-enter-active,.course-change-layer-leave-active{transition:opacity .2s ease}.course-change-layer-enter-active .course-change-workspace{transition:transform .34s cubic-bezier(.16,1,.3,1),filter .34s ease}.course-change-layer-enter-from,.course-change-layer-leave-to{opacity:0}.course-change-layer-enter-from .course-change-workspace{transform:translateY(18px) scale(.985);filter:blur(4px)}@keyframes spin{to{transform:rotate(360deg)}}@keyframes scan-sweep{from{transform:translateX(-100%)}to{transform:translateX(430%)}}@keyframes scan-item{from{transform:translateY(8px);opacity:0}to{transform:translateY(0);opacity:1}}@media(max-width:920px){.course-change-workspace{width:calc(100vw - 24px);height:calc(100dvh - 24px)}.course-identity{display:none}.workspace-header{grid-template-columns:40px minmax(180px,1fr) 38px 38px}.request-state,.scanning-state{grid-template-columns:minmax(0,1fr);width:min(720px,calc(100% - 32px))}.asset-ledger,.scanning-state>aside{display:none}.review-layout{grid-template-columns:190px minmax(0,1fr)}.structure-layout{grid-template-columns:minmax(0,1fr) 235px}.journey{padding-right:24px;padding-left:24px}}@media(prefers-reduced-motion:reduce){.course-change-layer-enter-active,.course-change-layer-leave-active,.course-change-layer-enter-active .course-change-workspace{transition:none}.scan-line span,.scanning-state>aside li{animation:none}}
.workspace-context-stack{min-height:0}.workspace-status-error{display:flex;align-items:center;gap:7px;margin:0;padding:9px 20px;border-bottom:1px solid #f3c7c3;color:#b42318;background:#fff4f2;font-size:11px}
.candidate-diff{display:grid;grid-template-columns:minmax(0,1fr) 18px minmax(0,1fr);align-items:center;gap:8px}.candidate-diff>svg{color:#667085}.source-preview.is-after{background:#edf8f4}.source-preview.is-after small{color:#087354}.candidate-error{display:flex;align-items:center;gap:5px;margin:8px 0 0;color:#b42318;font-size:9px}.receipt-items{display:grid;gap:6px;max-height:220px;overflow:auto;margin:0 0 18px;padding:0;text-align:left;list-style:none}.receipt-items li{display:grid;grid-template-columns:54px minmax(110px,.7fr) minmax(0,1.3fr);align-items:center;gap:8px;padding:8px 10px;border-radius:8px;background:#f6f7fa;font-size:9px}.receipt-items span{color:#667085;font-weight:800}.receipt-items li[data-status=applied] span{color:#087354}.receipt-items li[data-status=failed] span{color:#b42318}.receipt-items b{overflow:hidden;color:#253047;text-overflow:ellipsis;white-space:nowrap}.receipt-items small{color:#667085}

.course-change-layer.is-standalone{position:relative;inset:auto;z-index:1;width:100%;height:100%;display:block;padding:0;background:#f5f7fb}.is-standalone .course-change-workspace{width:100%;height:100%;display:flex;flex-direction:column;border-radius:0;box-shadow:none}.is-standalone .workspace-header{display:none}.is-standalone .journey,.is-standalone .workspace-context-stack{flex:none}.is-standalone .workspace-stage{flex:1}.is-standalone .course-change-workspace:focus{outline:none}
.course-change-layer.is-update-center{background:transparent}.is-update-center .course-change-workspace{background:#fff}.is-update-center .workspace-context-stack{border-bottom:1px solid #e2e6ed}.is-update-center .workspace-stage{background:#fff}.is-update-center .request-state{width:min(760px,calc(100% - 40px));padding-top:22px}.is-update-center .request-composer{box-shadow:none}.is-update-center .review-layout{grid-template-columns:210px minmax(0,1fr)}.is-update-center .impact-nav{padding:18px 14px}.is-update-center .impact-review{padding:18px 20px 0}.is-update-center .review-actionbar{margin:0 -20px}.is-update-center .structure-review{padding:20px 22px 34px}.is-update-center .migration-panel{padding:20px 16px}
.request-context{grid-template-columns:minmax(0,1fr) auto auto}.request-context>div{padding-left:0;border-right:0}.request-context>span{justify-self:end;padding:5px 8px;border-radius:7px;color:#5148dc;background:#ecebff;font-size:9px;font-weight:800}
.request-state{width:min(820px,calc(100% - 48px));grid-template-columns:minmax(0,1fr);align-content:start;gap:14px;padding:24px 0 42px}.request-composer{order:2;padding:24px 26px;border:1px solid #e3e7ef;box-shadow:0 10px 28px rgba(30,41,59,.055)}.request-heading{display:block;margin-bottom:16px}.request-heading h3{margin:0;font-size:22px}.request-composer form>textarea{min-height:154px}.request-composer form>footer{justify-content:flex-end}.request-composer form>footer>span{margin-right:auto;color:#b42318}.recent-changes{order:3;margin:0;padding:18px 4px 0;border-top:1px solid #dfe4ec}.readiness-strip{order:1;display:grid;gap:12px;padding:14px 16px;border:1px solid #e1e5ec;border-radius:13px;background:#fff}.readiness-strip>header{display:grid;grid-template-columns:28px minmax(0,1fr) auto;align-items:center;gap:9px}.readiness-strip>header>span{width:28px;height:28px;display:grid;place-items:center;border-radius:8px;color:#b54708;background:#fff3e6}.readiness-strip>header>span[data-ready=true]{color:#087354;background:#eaf8f2}.readiness-strip>header div{display:grid;gap:2px}.readiness-strip>header small{color:#667085;font-size:9px}.readiness-strip>header strong{color:#253047;font-size:12px}.readiness-strip>header>b{color:#5148dc;font-size:11px}.readiness-strip ul{display:flex;flex-wrap:wrap;gap:7px;margin:0;padding:0;list-style:none}.readiness-strip li{display:grid;grid-template-columns:7px auto auto;align-items:center;gap:5px;padding:5px 7px;border-radius:7px;color:#344054;background:#f5f6f8;font-size:9px}.readiness-strip li i{width:6px;height:6px;border-radius:50%;background:#16a36a}.readiness-strip li[data-state=partial] i,.readiness-strip li[data-state=stale] i{background:#d97706}.readiness-strip li[data-state=missing] i{background:#98a2b3}.readiness-strip li small{color:#667085}.migration-actions,.receipt-actions{display:grid;gap:8px}.migration-actions .button-primary,.migration-actions .button-secondary{width:100%}.receipt-actions{grid-template-columns:repeat(2,minmax(0,auto));justify-content:center;margin-top:8px}
@media(max-width:920px){.course-change-layer.is-standalone{height:100%}.is-standalone .course-change-workspace{width:100%;height:100%}.request-state{width:min(720px,calc(100% - 32px))}.readiness-strip ul{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.request-context{grid-template-columns:minmax(0,1fr) auto}.request-context>span{display:none}}
.receipt-state.is-partial-undo>section>svg{color:#b54708}
.button-danger{min-height:38px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 14px;border:1px solid #f0b9b3;border-radius:9px;color:#b42318;background:#fff;font-size:12px;font-weight:750;cursor:pointer}.button-danger:hover:not(:disabled){border-color:#d92d20;background:#fff4f2}.button-danger:disabled{opacity:.45;cursor:not-allowed}.compact-action{min-height:30px;padding:0 8px;font-size:10px}.impact-review{grid-template-rows:auto auto minmax(0,1fr) auto}.impact-tools{display:grid;grid-template-columns:minmax(180px,1fr) auto auto auto;align-items:center;gap:8px;padding:0 0 12px}.impact-tools>label{min-width:0;display:flex;align-items:center;gap:7px;padding:0 9px;border:1px solid #d4dae4;border-radius:8px;background:#fff}.impact-tools input{min-width:0;width:100%;height:32px;border:0;outline:0;color:#253047;background:transparent;font:inherit}.impact-tools>span{color:#667085;font-size:9px}.disposition-control{flex:none;display:grid;gap:3px}.disposition-control>span{color:#667085;font-size:8px;font-weight:700}.disposition-control select{height:30px;padding:0 25px 0 8px;border:1px solid #cfd5df;border-radius:7px;color:#4e46ce;background:#fff;font:700 9px inherit}.candidate-error{flex-wrap:wrap}.candidate-error button{padding:2px 5px;border:0;border-radius:5px;color:#b42318;background:#fee4e2;font:700 9px inherit;cursor:pointer}.review-actionbar{grid-template-columns:minmax(0,1fr) repeat(3,auto)}.tree-comparison{grid-template-columns:minmax(170px,.58fr) 20px minmax(430px,1.42fr)}.structure-editor>header{justify-content:flex-start}.structure-editor>header .compact-action{margin-left:auto}.tree-comparison .structure-edit-row{display:grid;grid-template-columns:minmax(130px,1fr) minmax(90px,.55fr);gap:7px;margin-left:calc(var(--tree-level) * 9px);padding:8px}.structure-edit-row>input,.structure-edit-row>select{min-width:0;height:31px;padding:0 8px;border:1px solid #cbd2de;border-radius:7px;color:#253047;background:#fff;font:600 10px inherit}.structure-edit-row>div{grid-column:1/-1;display:flex;align-items:center;gap:5px}.structure-edit-row>div>button{width:28px;height:28px;display:grid;place-items:center;padding:0;border:1px solid #d6dbe4;border-radius:7px;color:#596579;background:#fff;cursor:pointer}.structure-edit-row>div>button:hover:not(:disabled){color:#4e46ce;background:#f2f1ff}.structure-edit-row>div>button:disabled{opacity:.35}.structure-edit-row .merge-control{min-width:110px;max-width:190px;height:28px;padding:0 6px;border:1px solid #d6dbe4;border-radius:7px;color:#596579;background:#fff;font:600 9px inherit}.structure-editor .add-node{width:100%;margin-top:9px}.migration-actions .button-danger{width:100%}.receipt-actions{grid-template-columns:repeat(3,minmax(0,auto))}.receipt-items li[data-status=applied] span{color:#087354}
.impact-tools{grid-template-columns:minmax(180px,1fr) minmax(120px,.55fr) auto auto auto}.impact-tools>select{min-width:0;height:34px;padding:0 28px 0 9px;border:1px solid #d4dae4;border-radius:8px;color:#4f5d70;background:#fff;font:600 10px inherit}
@media(max-width:1100px){.impact-tools{grid-template-columns:minmax(160px,1fr) minmax(110px,.55fr) auto auto}.impact-tools>span{display:none}.review-actionbar{grid-template-columns:minmax(0,1fr) repeat(2,auto)}.tree-comparison{grid-template-columns:minmax(140px,.5fr) 16px minmax(360px,1.5fr)}}
.request-modes{display:flex;gap:8px;margin-bottom:16px}.request-modes button[aria-pressed=true]{color:var(--color-primary,#5148dc);border-color:currentColor}.literal-replacement{display:grid;gap:16px}.literal-replacement label{display:grid;gap:8px;font-size:15px}.literal-replacement input[type=text]{padding:10px;border:1px solid #cbd2de;border-radius:8px;font:inherit}.literal-replacement fieldset{display:flex;gap:16px;border:0;padding:0}.literal-replacement fieldset label{display:flex;align-items:center}.literal-replacement legend{margin-bottom:8px}.workspace-status-progress,.coverage-status{display:flex;align-items:center;gap:8px;margin:8px 20px;font-size:15px}.candidate-diff .source-preview p,.source-preview p{white-space:pre-wrap;display:block;-webkit-line-clamp:unset;overflow:visible;max-height:none;font-size:15px;line-height:1.7}.candidate-diff{align-items:start}.candidate-error{font-size:15px}.receipt-items li small{font-size:15px;white-space:normal}
.course-change-workspace .button-primary,.course-change-workspace .button-secondary,.course-change-workspace .button-danger,.course-change-workspace .button-quiet,
.course-change-workspace .request-suggestions button,.course-change-workspace .request-context button,
.course-change-workspace .impact-nav nav button,.course-change-workspace .impact-reason,.course-change-workspace .protected-scope p,
.course-change-workspace .recent-changes button,.course-change-workspace .receipt-items li,.course-change-workspace .candidate-error button{font-size:15px}
.course-change-workspace .impact-copy h4{font-size:17px}
.course-change-workspace .request-context p{font-size:15px;white-space:normal;overflow-wrap:anywhere}
.course-change-workspace .source-preview p{overflow-wrap:anywhere}
.course-change-workspace .review-actionbar{display:flex;flex-wrap:wrap;position:sticky;bottom:0;z-index:1}
.course-change-workspace .review-actionbar>div{flex:1 1 220px}
.course-change-workspace .impact-tools{display:flex;flex-wrap:wrap}
.course-change-workspace .impact-tools>label{flex:1 1 220px}
.course-change-workspace .impact-tools>select{flex:0 1 180px}
.course-change-workspace .candidate-error button{padding:6px 10px;border:1px solid #f0b9b3}
.course-change-workspace .button-secondary:disabled{opacity:.45;cursor:not-allowed}
.course-change-workspace button:focus-visible{outline:2px solid #5148dc;outline-offset:2px}
@media(prefers-reduced-motion:reduce){.spinning{animation:none}}
</style>
