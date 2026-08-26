<template>
  <section
    class="outline-review"
    :class="{ 'is-editing': editable }"
    :data-mode="editable ? 'edit' : 'view'"
    :data-variant="variant"
    :aria-label="t('courseGeneration.outlineReview.ariaLabel', '课程大纲')"
  >
    <article class="outline-review__sheet">
      <div v-if="loading" class="outline-review__loading" aria-live="polite">
        <LoaderCircle :size="18" />
        <span>{{ t('courseGeneration.outlineReview.loading', '正在载入可编辑目录') }}</span>
      </div>

      <div v-else-if="loadError" class="outline-review__load-error" role="alert">
        <TriangleAlert :size="17" />
        <div>
          <strong>{{ loadError }}</strong>
          <p>{{ t('courseGeneration.outlineReview.loadErrorHelp', '已生成结果仍然保留，重新载入不会重复创建课程。') }}</p>
        </div>
        <button type="button" @click="loadBlueprint">{{ t('courseGeneration.outlineReview.retry', '重试') }}</button>
      </div>

      <template v-else>
        <div class="outline-review__body">
          <div class="outline-review__setup" v-if="inlineSetupVisible">
          <section
            v-if="!isInline && coverageVerdict"
            class="outline-coverage"
            :data-status="coverageVerdict.status"
            data-testid="outline-coverage-verdict"
          >
            <header>
              <strong>{{ coverageHeadline }}</strong>
              <small v-if="coverageVerdict.class_hours">
                {{ t('courseGeneration.outlineReview.coverageHours', '{hours} 课时').replace('{hours}', String(coverageVerdict.class_hours)) }}
              </small>
            </header>
            <p v-if="coverageVerdict.coverage_promise">{{ coverageVerdict.coverage_promise }}</p>
            <div
              v-if="coverageUncovered.length"
              class="outline-coverage__uncovered"
              data-testid="outline-coverage-uncovered"
            >
              <span>{{ t('courseGeneration.outlineReview.coverageUncovered', '本次不覆盖') }}</span>
              <ul>
                <li v-for="topic in coverageUncovered" :key="topic">{{ topic }}</li>
              </ul>
            </div>
            <ul v-if="coverageAdvisories.length" class="outline-coverage__advisories">
              <li v-for="item in coverageAdvisories" :key="item">{{ item }}</li>
            </ul>
          </section>

          <section
            v-if="!isInline && retrievalProposal"
            class="outline-retrieval"
            data-testid="retrieval-outline-proposal"
          >
            <header>
              <div>
                <strong>{{ t('courseGeneration.outlineReview.retrievalTitle', '联网研究调整提案') }}</strong>
                <small>{{ t('courseGeneration.outlineReview.retrievalRevision', '检索包修订 {revision}').replace('{revision}', String(retrievalProposal.retrieval_package_revision || 1)) }}</small>
              </div>
              <span>{{ t('courseGeneration.outlineReview.retrievalPending', '确认目录后生效') }}</span>
            </header>
            <p>{{ retrievalProposal.reason || t('courseGeneration.outlineReview.retrievalReasonFallback', '外部资料建议调整当前课程结构。') }}</p>
            <div class="outline-retrieval__shape">
              <span>{{ shapeSummary(retrievalProposal.diff?.before) }}</span>
              <ArrowRight :size="13" />
              <span>{{ shapeSummary(retrievalProposal.diff?.after) }}</span>
            </div>
            <div class="outline-retrieval__diff">
              <section v-for="group in retrievalDiffGroups" :key="group.key" v-show="group.items.length">
                <h3>{{ group.label }}</h3>
                <ul>
                  <li v-for="item in group.items" :key="`${group.key}-${item.node_id || item.node_name}`">
                    <span>{{ item.node_name || item.title }}</span>
                    <small>{{ item.old_position && item.new_position
                      ? `${item.old_position} → ${item.new_position}`
                      : item.new_position || item.old_position || changedFieldSummary(item.changes) }}</small>
                  </li>
                </ul>
              </section>
            </div>
            <div v-if="retrievalProposal.sources?.length" class="outline-retrieval__sources">
              <a
                v-for="source in retrievalProposal.sources"
                v-show="safeExternalUrl(source.url)"
                :key="source.source_id"
                class="outline-retrieval__source"
                :href="safeExternalUrl(source.url)"
                target="_blank"
                rel="noopener noreferrer"
              >
                <strong>{{ source.title || source.domain }}</strong>
                <small>{{ source.domain }} · {{ source.trust_tier }}<template v-if="source.published_date"> · {{ source.published_date }}</template></small>
              </a>
            </div>
          </section>

          <section
            v-else-if="!isInline && (retrievalNotice || retrievalErrorKey)"
            class="outline-retrieval outline-retrieval--notice"
            data-testid="retrieval-outline-notice"
            role="status"
          >
            <div>
              <strong>{{ t('courseGeneration.outlineReview.retrievalIncomplete', '联网核验未完成') }}</strong>
              <p>{{ retrievalFailureDetail }}</p>
              <p v-if="retrievalFailureStats" class="outline-retrieval__stats">
                {{ retrievalFailureStats }}
              </p>
            </div>
            <button type="button" :disabled="retryingRetrieval" @click="retryRetrieval">
              <LoaderCircle v-if="retryingRetrieval" :size="14" />
              {{ retryingRetrieval
                ? t('courseGeneration.outlineReview.retrievalRetrying', '正在重试')
                : t('courseGeneration.outlineReview.retrievalRetry', '重试联网核验') }}
            </button>
            <small>{{ t('courseGeneration.outlineReview.retrievalOffline', '也可以直接确认当前本地蓝图，离线继续。') }}</small>
          </section>

          <section v-if="!isInline && isProjectCourse" class="outline-review__starting-point" :data-status="startingProfileStatus">
            <header>
              <span>{{ t('courseGeneration.outlineReview.startingPoint', '项目起点') }}</span>
              <strong>{{ startingProfileStatusLabel }}</strong>
            </header>
            <div>
              <p>
                <small>{{ t('courseGeneration.outlineReview.deliverable', '最终交付物') }}</small>
                <span>{{ projectDeliverable || t('courseGeneration.outlineReview.deliverablePending', '按项目目标确定') }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.experience', '已有经验') }}</small>
                <span>{{ startingStrengths || t('courseGeneration.outlineReview.notProvided', '暂未提供') }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.focusAreas', '重点补充') }}</small>
                <span>{{ startingFocus || t('courseGeneration.outlineReview.discoverInProject', '将在项目过程中继续识别') }}</span>
              </p>
            </div>
          </section>
          <section v-else-if="!isInline && courseType === 'inquiry'" class="outline-review__starting-point" data-status="tentative">
            <header>
              <span>{{ t('courseGeneration.outlineReview.inquiryContract', '探究信息') }}</span>
              <strong>{{ t('courseGeneration.outlineReview.inquiryGuard', '待验证') }}</strong>
            </header>
            <div>
              <p>
                <small>{{ t('courseGeneration.outlineReview.coreQuestion', '核心问题') }}</small>
                <span>{{ courseIntent.core_question }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.evidenceScope', '证据范围') }}</small>
                <span>{{ courseIntent.evidence_scope || t('courseGeneration.outlineReview.notProvided', '暂未提供') }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.desiredOutput', '结论形态') }}</small>
                <span>{{ courseIntent.desired_output }}</span>
              </p>
            </div>
          </section>

          <section v-else-if="!isInline && courseType === 'exam'" class="outline-review__starting-point" data-status="tentative">
            <header>
              <span>{{ t('courseGeneration.outlineReview.examContract', '考试信息') }}</span>
              <strong>{{ courseIntent.exam_date || t('courseGeneration.outlineReview.notProvided', '暂未提供') }}</strong>
            </header>
            <div>
              <p>
                <small>{{ t('courseGeneration.outlineReview.examName', '考试') }}</small>
                <span>{{ courseIntent.exam_name }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.examScope', '考纲范围') }}</small>
                <span>{{ courseIntent.exam_scope }}</span>
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.currentPreparation', '当前准备度') }}</small>
                <span>{{ courseIntent.current_preparation || t('courseGeneration.outlineReview.notProvided', '暂未提供') }}</span>
              </p>
            </div>
          </section>

          <section v-if="!assistantOpen && !isInline" class="outline-review__adjustment" :aria-busy="generatingProposal">
            <div class="outline-review__adjustment-heading">
              <label for="outline-adjustment-instruction">
                {{ t('courseGeneration.outlineReview.adjustmentTitle', '目录调整') }}
              </label>
            </div>
            <textarea
              id="outline-adjustment-instruction"
              v-model="adjustmentInstruction"
              rows="2"
              maxlength="3000"
              :disabled="adjustmentBusy"
              :placeholder="t('courseGeneration.outlineReview.adjustmentPlaceholder', '例如：把生命周期移到工程实践章最前面，再新增一节组件组合实战')"
            />
            <button
              type="button"
              data-testid="generate-outline-adjustment"
              :disabled="adjustmentBusy || !adjustmentInstruction.trim() || !blueprintNodes.length"
              @click="generateAdjustmentProposal"
            >
              <LoaderCircle v-if="generatingProposal" :size="15" />
              <Sparkles v-else :size="15" />
              {{ generatingProposal
                ? t('courseGeneration.outlineReview.adjustmentGenerating', '正在生成方案')
                : t('courseGeneration.outlineReview.adjustmentGenerate', '生成调整方案') }}
            </button>
          </section>

          <p v-if="proposalNotice" class="outline-review__proposal-notice" role="status">
            {{ proposalNotice }}
          </p>

          <section
            v-if="adjustmentProposal && !aiTargetNodeId"
            ref="proposalSummaryRef"
            class="outline-review__proposal"
            tabindex="-1"
            aria-labelledby="outline-adjustment-summary"
          >
            <details open>
              <summary id="outline-adjustment-summary">
                <span>{{ t('courseGeneration.outlineReview.proposalTitle', '调整方案预览') }}</span>
                <strong>
                  {{ shapeSummary(adjustmentProposal.diff?.before) }}
                  <ArrowRight :size="13" />
                  {{ shapeSummary(adjustmentProposal.diff?.after) }}
                </strong>
              </summary>
              <p class="outline-review__proposal-summary">{{ adjustmentProposal.summary }}</p>

              <div class="outline-review__diff-groups">
                <section v-if="adjustmentProposal.diff?.added?.length">
                  <h3>{{ t('courseGeneration.outlineReview.diffAdded', '新增') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.added" :key="`added-${item.node_id || item.node_name}`">
                      <span>{{ item.node_name }}</span><small>{{ item.new_position }}</small>
                    </li>
                  </ul>
                </section>
                <section v-if="adjustmentProposal.diff?.removed?.length">
                  <h3>{{ t('courseGeneration.outlineReview.diffRemoved', '删除') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.removed" :key="`removed-${item.node_id || item.node_name}`">
                      <span>{{ item.node_name }}</span><small>{{ item.old_position }}</small>
                    </li>
                  </ul>
                </section>
                <section v-if="adjustmentProposal.diff?.moved?.length">
                  <h3>{{ t('courseGeneration.outlineReview.diffMoved', '移动') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.moved" :key="`moved-${item.node_id || item.node_name}`">
                      <span>{{ item.node_name }}</span>
                      <small>{{ item.old_position }} → {{ item.new_position }}</small>
                    </li>
                  </ul>
                </section>
                <section v-if="adjustmentProposal.diff?.updated?.length">
                  <h3>{{ t('courseGeneration.outlineReview.diffUpdated', '内容修改') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.updated" :key="`updated-${item.node_id || item.node_name}`">
                      <span>{{ item.node_name }}</span>
                      <small>{{ changedFieldSummary(item.changes) }}</small>
                    </li>
                  </ul>
                </section>
              </div>

              <ul v-if="adjustmentProposal.blocking_issues?.length" class="outline-review__blockers" role="alert">
                <li v-for="issue in adjustmentProposal.blocking_issues" :key="issue.code || issue.message">
                  {{ issue.message }}
                </li>
              </ul>

              <div v-if="!assistantOpen" class="outline-review__proposal-actions">
                <button
                  type="button"
                  data-testid="cancel-outline-adjustment"
                  :disabled="applyingProposal"
                  @click="cancelAdjustmentProposal"
                >
                  {{ t('courseGeneration.outlineReview.proposalCancel', '取消') }}
                </button>
                <button
                  type="button"
                  class="primary"
                  data-testid="apply-outline-adjustment"
                  :disabled="applyingProposal || !adjustmentProposal.can_apply"
                  @click="applyAdjustmentProposal"
                >
                  <LoaderCircle v-if="applyingProposal" :size="15" />
                  {{ applyingProposal
                    ? t('courseGeneration.outlineReview.proposalApplying', '正在应用')
                    : t('courseGeneration.outlineReview.proposalApply', '应用整套方案') }}
                </button>
              </div>
            </details>
          </section>
          </div>

          <nav class="outline-view-switch" :aria-label="t('courseGeneration.outlineReview.viewSwitch', '大纲视图')">
            <button
              type="button"
              :class="{ active: viewMode === 'document' }"
              :aria-pressed="viewMode === 'document'"
              @click="viewMode = 'document'"
            >
              <FileText :size="14" />
              {{ t('courseGeneration.outlineReview.documentView', '正式大纲') }}
            </button>
            <button
              type="button"
              :class="{ active: viewMode === 'structure' }"
              :aria-pressed="viewMode === 'structure'"
              @click="viewMode = 'structure'"
            >
              <ListTree :size="14" />
              {{ t('courseGeneration.outlineReview.structureView', '课程结构') }}
            </button>
          </nav>

          <article v-if="viewMode === 'document' && blueprintNodes.length" class="formal-outline" data-testid="formal-outline-document">
            <header class="formal-outline__masthead">
              <div class="formal-outline__kicker">
                <FileText :size="15" />
                <span>{{ t('courseGeneration.outlineReview.documentKicker', '正式教学大纲') }}</span>
              </div>
              <h1>{{ documentTitle }}</h1>
              <p>{{ documentPositioning || t('courseGeneration.outlineReview.positioningPending', '课程定位将在教学目标与章节结构中继续明确。') }}</p>
              <dl>
                <div><dt>{{ t('courseGeneration.outlineReview.documentChapters', '章节') }}</dt><dd>{{ documentChapters.length }}</dd></div>
                <div><dt>{{ t('courseGeneration.outlineReview.documentSections', '小节') }}</dt><dd>{{ documentSectionCount }}</dd></div>
                <div><dt>{{ t('courseGeneration.outlineReview.documentQuality', '整篇审读') }}</dt><dd :data-ready="qualityReady">{{ qualityReady ? t('courseGeneration.outlineReview.qualityReady', '表达清晰') : t('courseGeneration.outlineReview.qualitySuggested', '建议优化') }}</dd></div>
              </dl>
            </header>

            <section class="formal-outline__brief">
              <div>
                <h2>{{ t('courseGeneration.outlineReview.courseOutcomes', '课程学习成果') }}</h2>
                <ol v-if="documentObjectives.length">
                  <li v-for="(objective, index) in documentObjectives" :key="`${index}-${objective}`">{{ objective }}</li>
                </ol>
                <p v-else>{{ t('courseGeneration.outlineReview.outcomesPending', '暂未形成独立的全课成果条目。') }}</p>
              </div>
              <div>
                <h2>{{ t('courseGeneration.outlineReview.prerequisites', '先修要求') }}</h2>
                <ul v-if="documentPrerequisites.length">
                  <li v-for="(item, index) in documentPrerequisites" :key="`${index}-${item}`">{{ item }}</li>
                </ul>
                <p v-else>{{ t('courseGeneration.outlineReview.noPrerequisites', '无明确先修要求；按课程内学习路径逐步建立基础。') }}</p>
              </div>
            </section>

            <section v-if="qualityIssues.length" class="outline-quality" aria-labelledby="outline-quality-title">
              <header>
                <div>
                  <span>{{ t('courseGeneration.outlineReview.qualityEyebrow', '整篇审读') }}</span>
                  <h2 id="outline-quality-title">{{ t('courseGeneration.outlineReview.qualityTitle', '让每一节都更像专业教学设计') }}</h2>
                </div>
                <p>{{ qualityArtifact.summary }}</p>
              </header>
              <ol>
                <li v-for="issue in qualityIssues" :key="issue.code">
                  <div>
                    <strong>{{ issue.message }}</strong>
                    <small>{{ qualityIssueLocation(issue) }}</small>
                  </div>
                  <button
                    v-if="qualityIssueActionable(issue)"
                    type="button"
                    :disabled="adjustmentBusy || !!adjustmentProposal"
                    @click="repairQualityIssue(issue)"
                  >
                    <LoaderCircle v-if="repairingQualityCode === issue.code" :size="14" />
                    <Sparkles v-else :size="14" />
                    {{ t('courseGeneration.outlineReview.targetedRepair', '定点优化') }}
                  </button>
                </li>
              </ol>
              <footer>{{ t('courseGeneration.outlineReview.qualityNonBlocking', '这些是非阻断建议；原大纲仍可继续编辑和确认。') }}</footer>
            </section>

            <section class="formal-outline__schedule">
              <header>
                <div>
                  <span>{{ t('courseGeneration.outlineReview.scheduleKicker', '教学进度') }}</span>
                  <h2>{{ t('courseGeneration.outlineReview.scheduleTitle', '章节与学习任务安排') }}</h2>
                </div>
                <p>{{ t('courseGeneration.outlineReview.scheduleDescription', '每个小节都对应一项可观察目标与达成检验。') }}</p>
              </header>
              <article v-for="(chapter, chapterIndex) in documentChapters" :key="chapter.node_id || chapter.chapter_number || chapterIndex" class="formal-outline__chapter-block">
                <header>
                  <span>{{ String(chapterIndex + 1).padStart(2, '0') }}</span>
                  <div>
                    <h3>{{ plainOutlineTitle(chapter.title) }}</h3>
                    <p v-if="chapter.learning_focus || chapter.learning_objective">{{ chapter.learning_focus || chapter.learning_objective }}</p>
                  </div>
                  <small>{{ (chapter.sections || []).length }} {{ t('courseWorkbench.form.sectionUnit', '小节') }}</small>
                </header>
                <ol>
                  <li v-for="(section, sectionIndex) in chapter.sections || []" :key="section.node_id || section.section_number || sectionIndex">
                    <span>{{ section.section_number || `${chapterIndex + 1}.${sectionIndex + 1}` }}</span>
                    <div>
                      <h4>{{ plainOutlineTitle(section.title || section.node_name) }}</h4>
                      <p>{{ section.learning_objective || t('courseGeneration.outlineReview.objectivePending', '学习目标待完善') }}</p>
                      <p v-if="section.scope_boundary" class="formal-outline__boundary">{{ section.scope_boundary }}</p>
                      <div v-if="assessmentItems(section.assessment).length" class="formal-outline__assessment">
                        <strong>{{ t('courseGeneration.outlineReview.assessmentLabel', '达成检验') }}</strong>
                        <span>{{ assessmentItems(section.assessment).join('；') }}</span>
                      </div>
                    </div>
                  </li>
                </ol>
              </article>
            </section>
          </article>

          <div class="outline-review__chapters" v-show="viewMode === 'structure'" ref="chaptersRef" data-testid="outline-chapter-list">
            <div class="outline-review__list-toolbar">
              <strong v-if="!isInline">{{ t('courseGeneration.outlineReview.manualEditTitle', '课程结构') }}</strong>
              <div class="outline-review__toolbar-actions">
                <button v-if="!isInline || editable" data-testid="add-outline-chapter" type="button" :disabled="adjustmentBusy" @click="addChapter">
                  <Plus :size="14" />{{ t('courseGeneration.outlineReview.addChapter', '新增章') }}
                </button>
              </div>
            </div>
            <section
              v-for="(group, groupIndex) in outlineGroups"
              :key="group.key"
              class="outline-review__chapter"
              :class="{
                'outline-review__chapter--ungrouped': !group.chapter,
                'is-selected': group.chapter && selectedNodeId === String(group.chapter.node.node_id || ''),
              }"
            >
              <header
                v-if="group.chapter"
                class="outline-review__chapter-heading"
                @click.stop="selectOutlineNode(group.chapter.node)"
                @focusin="selectOutlineNode(group.chapter.node)"
              >
                <span v-if="isInline" class="outline-review__chapter-index">{{ String(groupIndex + 1).padStart(2, '0') }}</span>
                <div v-if="!isInline && group.chapter.node.learning_path_role" class="outline-review__node-meta">
                  <span :data-role="normalizedPathRole(group.chapter.node.learning_path_role)">
                    {{ pathRoleLabel(group.chapter.node.learning_path_role) }}
                  </span>
                  <p v-if="group.chapter.node.path_reason">{{ group.chapter.node.path_reason }}</p>
                </div>
                <div class="outline-review__node-fields">
                  <input
                    v-model="group.chapter.node.node_name"
                    :data-outline-node-id="String(group.chapter.node.node_id || '')"
                    type="text"
                    :disabled="adjustmentBusy"
                    :readonly="isInline && !editable"
                    :tabindex="isInline && !editable ? -1 : undefined"
                    :aria-label="t('courseTasks.blueprint.nodeName', '章节名称')"
                    @input="invalidateProposal"
                  />
                  <p
                    v-if="'learning_objective' in group.chapter.node && isInline && !editable"
                    class="outline-review__objective-text"
                  >{{ group.chapter.node.learning_objective || t('courseGeneration.outlineReview.objectivePlaceholder', '学习目标（可选）') }}</p>
                  <textarea
                    v-else-if="'learning_objective' in group.chapter.node"
                    v-model="group.chapter.node.learning_objective"
                    rows="1"
                    :disabled="adjustmentBusy"
                    :readonly="isInline && !editable"
                    :tabindex="isInline && !editable ? -1 : undefined"
                    :placeholder="t('courseGeneration.outlineReview.objectivePlaceholder', '学习目标（可选）')"
                    :aria-label="t('courseTasks.blueprint.objective', '学习目标')"
                    @input="invalidateProposal"
                  />
                </div>
                <div v-if="!isInline || editable" class="outline-review__node-actions">
                  <button
                    v-if="selectedNodeId === String(group.chapter.node.node_id || '')"
                    type="button"
                    class="outline-review__node-ai"
                    data-testid="outline-node-ai-action"
                    :title="t('courseGeneration.outlineReview.aiModifyNode', '让 AI 修改这一块')"
                    :aria-label="t('courseGeneration.outlineReview.aiModifyChapter', '让 AI 修改本章')"
                    :disabled="adjustmentBusy || !!adjustmentProposal"
                    @click.stop="openNodeAi(group.chapter.node)"
                  ><Sparkles :size="14" /><span>{{ t('courseGeneration.outlineReview.aiModifyShort', 'AI 修改') }}</span></button>
                  <button type="button" :title="t('courseGeneration.outlineReview.addSection', '新增小节')" :disabled="adjustmentBusy" @click="addSection(group.chapter.node)"><Plus :size="14" /></button>
                  <button type="button" :title="t('courseGeneration.outlineReview.moveUp', '上移')" :disabled="adjustmentBusy || !canMoveNode(group.chapter.node, -1)" @click="moveOutlineNode(group.chapter.node, -1)"><ArrowUp :size="14" /></button>
                  <button type="button" :title="t('courseGeneration.outlineReview.moveDown', '下移')" :disabled="adjustmentBusy || !canMoveNode(group.chapter.node, 1)" @click="moveOutlineNode(group.chapter.node, 1)"><ArrowDown :size="14" /></button>
                  <button type="button" class="danger" :title="t('courseGeneration.outlineReview.removeChapter', '删除本章')" :disabled="adjustmentBusy" @click="removeOutlineNode(group.chapter.node)"><Trash2 :size="14" /></button>
                </div>
              </header>

              <section
                v-if="group.chapter && aiTargetNodeId === String(group.chapter.node.node_id || '')"
                class="outline-review__node-ai-panel"
                :aria-busy="generatingProposal || applyingProposal"
                @click.stop
              >
                <template v-if="!adjustmentProposal">
                  <div class="outline-review__node-ai-quick-actions">
                    <button type="button" :disabled="adjustmentBusy" @click="runNodeAiPreset(group.chapter.node, '优化本章标题和学习目标，使表达更准确、简洁')">{{ t('courseGeneration.outlineReview.aiPolish', '优化表达') }}</button>
                    <button type="button" :disabled="adjustmentBusy" @click="runNodeAiPreset(group.chapter.node, '细化本章学习目标，使其具体、可观察、可检查')">{{ t('courseGeneration.outlineReview.aiRefineObjective', '细化目标') }}</button>
                  </div>
                  <div class="outline-review__node-ai-input">
                    <Sparkles :size="15" />
                    <input
                      v-model="nodeAiInstruction"
                      type="text"
                      maxlength="1200"
                      :disabled="adjustmentBusy || !!adjustmentProposal"
                      :placeholder="t('courseGeneration.outlineReview.aiNodePlaceholder', '告诉 AI 这一块要怎么改')"
                      @keydown.enter.prevent="runNodeAi(group.chapter.node)"
                    />
                    <button type="button" :disabled="adjustmentBusy || !nodeAiInstruction.trim()" @click="runNodeAi(group.chapter.node)">
                      <LoaderCircle v-if="generatingProposal" :size="14" />
                      <ArrowRight v-else :size="14" />
                      {{ t('courseGeneration.outlineReview.aiGenerate', '生成修改') }}
                    </button>
                  </div>
                </template>
                <div v-else class="outline-review__node-proposal" data-testid="outline-node-ai-proposal">
                  <div>
                    <Sparkles :size="15" /><strong>{{ t('courseGeneration.outlineReview.aiProposal', 'AI 修改建议') }}</strong><span>{{ adjustmentProposal.summary }}</span>
                    <small v-if="adjustmentProposal.blocking_issues?.length" role="alert">{{ adjustmentProposal.blocking_issues[0].message }}</small>
                  </div>
                  <div v-if="nodeProposalChanges(String(group.chapter.node.node_id || '')).length" class="outline-review__node-diff">
                    <div v-for="change in nodeProposalChanges(String(group.chapter.node.node_id || ''))" :key="change.field">
                      <strong>{{ change.label }}</strong>
                      <del>{{ proposalValue(change.before) }}</del>
                      <ArrowRight :size="13" />
                      <ins>{{ proposalValue(change.after) }}</ins>
                    </div>
                  </div>
                  <div class="outline-review__node-proposal-actions">
                    <button type="button" :disabled="applyingProposal" @click="cancelAdjustmentProposal">{{ t('courseGeneration.outlineReview.proposalCancel', '放弃') }}</button>
                    <button type="button" class="primary" :disabled="applyingProposal || !adjustmentProposal.can_apply" @click="applyAdjustmentProposal">
                      <LoaderCircle v-if="applyingProposal" :size="14" />
                      {{ applyingProposal ? t('courseGeneration.outlineReview.proposalApplying', '正在采用') : t('courseGeneration.outlineReview.applyNodeProposal', '采用修改') }}
                    </button>
                  </div>
                </div>
              </section>

              <div v-if="group.sections.length" class="outline-review__section-list">
                <article
                  v-for="(item, sectionIndex) in group.sections"
                  :key="item.node.node_id || item.index"
                  class="outline-review__section"
                  :class="{ 'is-selected': selectedNodeId === String(item.node.node_id || '') }"
                  @click.stop="selectOutlineNode(item.node)"
                  @focusin="selectOutlineNode(item.node)"
                >
                  <span v-if="isInline" class="outline-review__section-index">{{ groupIndex + 1 }}.{{ sectionIndex + 1 }}</span>
                  <div v-if="!isInline && item.node.learning_path_role" class="outline-review__node-meta">
                    <span :data-role="normalizedPathRole(item.node.learning_path_role)">
                      {{ pathRoleLabel(item.node.learning_path_role) }}
                    </span>
                    <p v-if="item.node.path_reason">{{ item.node.path_reason }}</p>
                  </div>
                  <div class="outline-review__node-fields">
                  <input
                    v-model="item.node.node_name"
                    :data-outline-node-id="String(item.node.node_id || '')"
                    type="text"
                      :disabled="adjustmentBusy"
                      :readonly="isInline && !editable"
                      :tabindex="isInline && !editable ? -1 : undefined"
                      :aria-label="t('courseTasks.blueprint.nodeName', '章节名称')"
                      @input="invalidateProposal"
                    />
                    <p
                      v-if="isInline && !editable"
                      class="outline-review__objective-text"
                    >{{ item.node.learning_objective || t('courseGeneration.outlineReview.objectivePlaceholder', '学习目标（可选）') }}</p>
                    <textarea
                      v-else
                      v-model="item.node.learning_objective"
                      rows="1"
                      :disabled="adjustmentBusy"
                      :readonly="isInline && !editable"
                      :tabindex="isInline && !editable ? -1 : undefined"
                      :placeholder="t('courseGeneration.outlineReview.objectivePlaceholder', '学习目标（可选）')"
                      :aria-label="t('courseTasks.blueprint.objective', '学习目标')"
                      @input="invalidateProposal"
                    />
                  </div>
                  <div v-if="!isInline || editable" class="outline-review__node-actions">
                    <button
                      v-if="selectedNodeId === String(item.node.node_id || '')"
                      type="button"
                      class="outline-review__node-ai"
                      data-testid="outline-node-ai-action"
                      :title="t('courseGeneration.outlineReview.aiModifyNode', '让 AI 修改这一块')"
                      :aria-label="t('courseGeneration.outlineReview.aiModifySection', '让 AI 修改本小节')"
                      :disabled="adjustmentBusy || !!adjustmentProposal"
                      @click.stop="openNodeAi(item.node)"
                    ><Sparkles :size="14" /><span>{{ t('courseGeneration.outlineReview.aiModifyShort', 'AI 修改') }}</span></button>
                    <button type="button" :title="t('courseGeneration.outlineReview.moveUp', '上移')" :disabled="adjustmentBusy || !canMoveNode(item.node, -1)" @click="moveOutlineNode(item.node, -1)"><ArrowUp :size="14" /></button>
                    <button type="button" :title="t('courseGeneration.outlineReview.moveDown', '下移')" :disabled="adjustmentBusy || !canMoveNode(item.node, 1)" @click="moveOutlineNode(item.node, 1)"><ArrowDown :size="14" /></button>
                    <button type="button" class="danger" :title="t('courseGeneration.outlineReview.removeSection', '删除小节')" :disabled="adjustmentBusy" @click="removeOutlineNode(item.node)"><Trash2 :size="14" /></button>
                  </div>
                  <section
                    v-if="aiTargetNodeId === String(item.node.node_id || '')"
                    class="outline-review__node-ai-panel"
                    :aria-busy="generatingProposal || applyingProposal"
                    @click.stop
                  >
                    <template v-if="!adjustmentProposal">
                      <div class="outline-review__node-ai-quick-actions">
                        <button type="button" :disabled="adjustmentBusy" @click="runNodeAiPreset(item.node, '优化本小节标题和学习目标，使表达更准确、简洁')">{{ t('courseGeneration.outlineReview.aiPolish', '优化表达') }}</button>
                        <button type="button" :disabled="adjustmentBusy" @click="runNodeAiPreset(item.node, '细化本小节学习目标，使其具体、可观察、可检查')">{{ t('courseGeneration.outlineReview.aiRefineObjective', '细化目标') }}</button>
                      </div>
                      <div class="outline-review__node-ai-input">
                        <Sparkles :size="15" />
                        <input
                          v-model="nodeAiInstruction"
                          type="text"
                          maxlength="1200"
                          :disabled="adjustmentBusy"
                          :placeholder="t('courseGeneration.outlineReview.aiNodePlaceholder', '告诉 AI 这一块要怎么改')"
                          @keydown.enter.prevent="runNodeAi(item.node)"
                        />
                        <button type="button" :disabled="adjustmentBusy || !nodeAiInstruction.trim()" @click="runNodeAi(item.node)">
                          <LoaderCircle v-if="generatingProposal" :size="14" />
                          <ArrowRight v-else :size="14" />
                          {{ t('courseGeneration.outlineReview.aiGenerate', '生成修改') }}
                        </button>
                      </div>
                    </template>
                    <div v-else class="outline-review__node-proposal" data-testid="outline-node-ai-proposal">
                      <div>
                        <Sparkles :size="15" /><strong>{{ t('courseGeneration.outlineReview.aiProposal', 'AI 修改建议') }}</strong><span>{{ adjustmentProposal.summary }}</span>
                        <small v-if="adjustmentProposal.blocking_issues?.length" role="alert">{{ adjustmentProposal.blocking_issues[0].message }}</small>
                      </div>
                      <div v-if="nodeProposalChanges(String(item.node.node_id || '')).length" class="outline-review__node-diff">
                        <div v-for="change in nodeProposalChanges(String(item.node.node_id || ''))" :key="change.field">
                          <strong>{{ change.label }}</strong>
                          <del>{{ proposalValue(change.before) }}</del>
                          <ArrowRight :size="13" />
                          <ins>{{ proposalValue(change.after) }}</ins>
                        </div>
                      </div>
                      <div class="outline-review__node-proposal-actions">
                        <button type="button" :disabled="applyingProposal" @click="cancelAdjustmentProposal">{{ t('courseGeneration.outlineReview.proposalCancel', '放弃') }}</button>
                        <button type="button" class="primary" :disabled="applyingProposal || !adjustmentProposal.can_apply" @click="applyAdjustmentProposal">
                          <LoaderCircle v-if="applyingProposal" :size="14" />
                          {{ applyingProposal ? t('courseGeneration.outlineReview.proposalApplying', '正在采用') : t('courseGeneration.outlineReview.applyNodeProposal', '采用修改') }}
                        </button>
                      </div>
                    </div>
                  </section>
                </article>
              </div>
            </section>
          </div>

          <p v-if="!blueprintNodes.length" class="outline-review__empty">
            {{ t('courseGeneration.outlineReview.empty', '目录尚未形成，请重新载入后再确认。') }}
          </p>
        </div>
      </template>

      <footer class="outline-review__footer" v-if="!isInline || requiresConfirmation || (editable && dirty) || (isInline && surface === 'teacher' && !editable) || actionError">
        <p v-if="actionError" class="outline-review__action-error" role="alert">{{ actionError }}</p>
        <div class="outline-review__actions">
          <span
            v-if="editable && !dirty && !saving && !loading && blueprintNodes.length"
            class="outline-review__saved-state"
            role="status"
          >
            <CircleCheck :size="15" />
            {{ t('courseGeneration.outlineReview.savedState', '已保存') }}
          </span>
          <button
            v-else-if="editable"
            type="button"
            class="secondary"
            :disabled="loading || acting || !!adjustmentProposal || !dirty || !blueprintNodes.length"
            @click="saveDraft"
          >
            <LoaderCircle v-if="saving" :size="15" />
            <Save v-else :size="15" />
            {{ saving
              ? t('courseGeneration.outlineReview.saving', '保存中')
              : t('courseGeneration.outlineReview.save', '保存修改') }}
          </button>
          <button
            v-if="!isInline || requiresConfirmation"
            type="button"
            class="primary"
            :disabled="loading || acting || !!adjustmentProposal || !blueprintNodes.length"
            @click="confirmOutline"
          >
            <LoaderCircle v-if="confirming" :size="15" />
            <CircleCheck v-else :size="15" />
            {{ surface === 'teacher'
              ? t('courseWorkbench.confirmOutline', '确认课程大纲')
              : t('courseGeneration.gate.confirmOutline', '确认目录并继续') }}
          </button>
        </div>
      </footer>
    </article>
    <span class="outline-review__sr-only" aria-live="polite">{{ liveStatus }}</span>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowDown, ArrowRight, ArrowUp, CircleCheck, FileText, ListTree, LoaderCircle, Plus, Save, Sparkles, Trash2, TriangleAlert } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import type { Node, Task } from '../stores/types'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { t } from '../shared/i18n'
import { retrievalErrorTranslationKey } from '../utils/retrieval-errors'

const props = withDefaults(defineProps<{
  courseId: string
  courseName?: string
  nodes?: Node[]
  task?: Task
  surface?: 'student' | 'teacher'
  editable?: boolean
  variant?: 'full' | 'inline'
  requiresConfirmation?: boolean
  assistantOpen?: boolean
}>(), {
  courseName: '',
  nodes: () => [],
  task: undefined,
  surface: 'student',
  editable: true,
  variant: 'full',
  requiresConfirmation: true,
  assistantOpen: false,
})

const emit = defineEmits<{
  (event: 'confirmed'): void
  (event: 'open-ai'): void
  (event: 'ai-candidate-change', candidate: Record<string, any> | null): void
  (event: 'ai-resolving', result: { accept: boolean }): void
  (event: 'ai-resolved', result: { accept: boolean }): void
  (event: 'ai-error', message: string): void
}>()

const courseStore = useCourseStore()
const workspace = useCourseWorkspaceStore()
const generationStore = useGenerationStore()
const blueprintDraft = ref<Record<string, any>>({})
const retrievalArtifact = ref<Record<string, any>>({})
// D-1：课程规格与覆盖度判定。只在后端真的给出判定时展示——没有判定时保持沉默，
// 而不是显示"完整"，因为"沉默被当成完整"正是这个问题的由来。
const coverageArtifact = ref<Record<string, any>>({})
const qualityArtifact = ref<Record<string, any>>({})
const viewMode = ref<'document' | 'structure'>('document')
const repairingQualityCode = ref('')
const coverageVerdict = computed(() => (
  coverageArtifact.value?.available ? coverageArtifact.value : null
))
const coverageUncovered = computed<string[]>(() => (
  Array.isArray(coverageVerdict.value?.uncovered_topics)
    ? coverageVerdict.value.uncovered_topics.map((item: any) => String(item))
    : []
))
const coverageAdvisories = computed<string[]>(() => (
  Array.isArray(coverageVerdict.value?.advisories)
    ? coverageVerdict.value.advisories.map((item: any) => String(item))
    : []
))
const coverageHeadline = computed(() => {
  const verdict = coverageVerdict.value
  if (!verdict) return ''
  const label = String(verdict.scale_label || '')
  if (verdict.may_claim_complete_subject) {
    return t(
      'courseGeneration.outlineReview.coverageComplete',
      '本次为{label}，可按完整课程组织',
    ).replace('{label}', label)
  }
  return t(
    'courseGeneration.outlineReview.coveragePartial',
    '本次为{label}，不承担学科完整覆盖',
  ).replace('{label}', label)
})
const baseline = ref('')
const loading = ref(false)
const saving = ref(false)
const confirming = ref(false)
const loadError = ref('')
const actionError = ref('')
const adjustmentInstruction = ref('')
const adjustmentProposal = ref<Record<string, any> | null>(null)
const generatingProposal = ref(false)
const applyingProposal = ref(false)
const retryingRetrieval = ref(false)
const proposalNotice = ref('')
const liveStatus = ref('')
const proposalSummaryRef = ref<HTMLElement | null>(null)
const chaptersRef = ref<HTMLElement | null>(null)
const adjustmentRequestId = ref('')
const selectedNodeId = ref('')
const aiTargetNodeId = ref('')
const nodeAiInstruction = ref('')

const isInline = computed(() => props.variant === 'inline')
const inlineSetupVisible = computed(() => !isInline.value || Boolean(
  adjustmentProposal.value && !aiTargetNodeId.value,
))
const adjustmentBusy = computed(() => generatingProposal.value || applyingProposal.value)
const retrievalProposal = computed<Record<string, any> | null>(() => (
  retrievalArtifact.value?.proposal || null
))
const retrievalNotice = computed(() => String(retrievalArtifact.value?.notice || '').trim())
const retrievalErrorKey = computed(() => retrievalErrorTranslationKey(retrievalArtifact.value))
const retrievalFailureDetail = computed(() => {
  return retrievalErrorKey.value
    ? t(retrievalErrorKey.value, retrievalNotice.value)
    : retrievalNotice.value
})
const retrievalPackage = computed<Record<string, any>>(() => (
  retrievalArtifact.value?.package
  || retrievalArtifact.value?.retrieval_package
  || retrievalArtifact.value
  || {}
))
const retrievalFailureStats = computed(() => {
  const receipt = retrievalPackage.value?.receipt || {}
  const admittedValue = Number(receipt.admitted_count ?? receipt.source_count ?? 0)
  const admitted = Number.isFinite(admittedValue) ? Math.max(0, admittedValue) : 0
  const rejectedSources = retrievalPackage.value?.rejected_sources
  const rejectedValue = Array.isArray(rejectedSources)
    ? rejectedSources.length
    : Number(receipt.tier_distribution?.tier_c ?? 0)
  const rejected = Number.isFinite(rejectedValue) ? Math.max(0, rejectedValue) : 0
  const total = admitted + rejected
  if (total <= 0) return ''
  return t(
    'courseGeneration.outlineReview.retrievalStats',
    '已检查 {total} 个候选来源，其中 {admitted} 个符合准入标准。',
  )
    .replace('{total}', String(total))
    .replace('{admitted}', String(admitted))
})
const retrievalDiffGroups = computed(() => {
  const diff = retrievalProposal.value?.diff || {}
  return [
    { key: 'added', label: t('courseGeneration.outlineReview.diffAdded', '新增'), items: diff.added || [] },
    { key: 'removed', label: t('courseGeneration.outlineReview.diffRemoved', '删除'), items: diff.removed || [] },
    { key: 'moved', label: t('courseGeneration.outlineReview.diffMoved', '移动'), items: diff.moved || [] },
    { key: 'updated', label: t('courseGeneration.outlineReview.diffUpdated', '内容修改'), items: diff.updated || [] },
  ]
})
const acting = computed(() => saving.value || confirming.value || adjustmentBusy.value)
const blueprintNodes = computed<any[]>(() => (
  Array.isArray(blueprintDraft.value?.nodes)
    ? blueprintDraft.value.nodes
    : Array.isArray(blueprintDraft.value?.course_blueprint?.nodes)
      ? blueprintDraft.value.course_blueprint.nodes
      : []
))
const outlineGroups = computed(() => {
  const chapters = blueprintNodes.value
    .map((node, index) => ({ node, index }))
    .filter(item => Number(item.node.node_level || 2) === 1)
    .map(item => ({
      key: String(item.node.node_id || `chapter-${item.index}`),
      chapter: item,
      sections: [] as Array<{ node: any; index: number }>,
    }))
  const chapterById = new Map(chapters.map(group => [String(group.chapter.node.node_id || ''), group]))
  const ungrouped = {
    key: 'ungrouped-sections',
    chapter: null as null,
    sections: [] as Array<{ node: any; index: number }>,
  }

  blueprintNodes.value.forEach((node, index) => {
    if (Number(node.node_level || 2) === 1) return
    const parent = chapterById.get(String(node.parent_node_id || ''))
    ;(parent || ungrouped).sections.push({ node, index })
  })

  return ungrouped.sections.length ? [...chapters, ungrouped] : chapters
})
const documentPlan = computed<Record<string, any>>(() => (
  blueprintDraft.value?.course_plan
  || blueprintDraft.value?.course_outline
  || {}
))
const documentTitle = computed(() => String(
  documentPlan.value.course_title
  || blueprintDraft.value?.course_name
  || props.courseName
  || t('courseGeneration.outlineReview.documentFallbackTitle', '课程教学大纲'),
))
const documentPositioning = computed(() => String(documentPlan.value.positioning || '').trim())
const documentObjectives = computed<string[]>(() => (
  Array.isArray(documentPlan.value.learning_objectives)
    ? documentPlan.value.learning_objectives.map((item: any) => String(item || '').trim()).filter(Boolean)
    : []
))
const documentPrerequisites = computed<string[]>(() => (
  Array.isArray(documentPlan.value.prerequisites)
    ? documentPlan.value.prerequisites.map((item: any) => String(item || '').trim()).filter(Boolean)
    : []
))
const documentChapters = computed<any[]>(() => (
  Array.isArray(documentPlan.value.chapters) && documentPlan.value.chapters.length
    ? documentPlan.value.chapters
    : outlineGroups.value.map((group, chapterIndex) => ({
      chapter_number: chapterIndex + 1,
      title: group.chapter?.node.node_name || '',
      learning_focus: group.chapter?.node.learning_objective || '',
      sections: group.sections.map(({ node }, sectionIndex) => ({
        ...node,
        section_number: `${chapterIndex + 1}.${sectionIndex + 1}`,
        title: node.node_name,
      })),
    }))
))
const documentSectionCount = computed(() => documentChapters.value.reduce(
  (total, chapter) => total + (Array.isArray(chapter.sections) ? chapter.sections.length : 0),
  0,
))
const qualityIssues = computed<any[]>(() => (
  Array.isArray(qualityArtifact.value?.issues) ? qualityArtifact.value.issues : []
))
const qualityReady = computed(() => qualityArtifact.value?.status === 'ready' || !qualityIssues.value.length)
const courseType = computed(() => String(blueprintDraft.value?.course_type || props.task?.courseType || 'systematic'))
const isProjectCourse = computed(() => courseType.value === 'project')
const courseIntent = computed<Record<string, any>>(() => blueprintDraft.value?.course_intent || {})
const startingProfile = computed<Record<string, any>>(() => blueprintDraft.value?.learner_starting_profile || {})
const startingProfileStatus = computed(() => String(startingProfile.value.status || 'insufficient'))
const projectDeliverable = computed(() => String(courseIntent.value.expected_deliverable || '').trim())
const startingStrengths = computed(() => listText(startingProfile.value.self_reported_strengths))
const startingFocus = computed(() => listText(startingProfile.value.focus_areas))
const startingProfileStatusLabel = computed(() => startingProfileStatus.value === 'insufficient'
  ? t('courseGeneration.outlineReview.startingPointInsufficient', '起点信息不足')
  : t('courseGeneration.outlineReview.startingPointTentative', '暂定起点'))
const draftSignature = computed(() => JSON.stringify({
  course_name: blueprintDraft.value?.course_name || '',
  nodes: blueprintNodes.value.map(node => ({
    node_id: node.node_id,
    parent_node_id: node.parent_node_id,
    node_name: node.node_name,
    node_level: node.node_level,
    learning_objective: node.learning_objective || '',
    scope_boundary: node.scope_boundary || '',
    assessment: node.assessment || [],
    prerequisite_node_ids: node.prerequisite_node_ids || [],
  })),
}))
const dirty = computed(() => Boolean(baseline.value && draftSignature.value !== baseline.value))

onMounted(() => {
  viewMode.value = props.editable ? 'structure' : 'document'
  void loadBlueprint()
})
watch(() => props.courseId, (courseId, previous) => {
  if (courseId && courseId !== previous) void loadBlueprint()
})
watch(() => props.editable, editable => {
  viewMode.value = editable ? 'structure' : 'document'
  if (!editable) {
    selectedNodeId.value = ''
    aiTargetNodeId.value = ''
    nodeAiInstruction.value = ''
  }
})

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

function listText(value: unknown) {
  if (!Array.isArray(value)) return ''
  return value.map(item => String(item || '').trim()).filter(Boolean).join('；')
}

function normalizedPathRole(value: unknown) {
  const role = String(value || '')
  return ['focus', 'standard', 'compressed', 'verify_in_project', 'milestone'].includes(role)
    ? role
    : 'standard'
}

function pathRoleLabel(value: unknown) {
  const labels = {
    focus: t('courseGeneration.outlineReview.pathRoles.focus', '重点补充'),
    standard: t('courseGeneration.outlineReview.pathRoles.standard', '正常学习'),
    compressed: t('courseGeneration.outlineReview.pathRoles.compressed', '快速通过'),
    verify_in_project: t('courseGeneration.outlineReview.pathRoles.verifyInProject', '项目中验证'),
    milestone: t('courseGeneration.outlineReview.pathRoles.milestone', '项目节点'),
  }
  return labels[normalizedPathRole(value) as keyof typeof labels]
}

function seedNodesFromCourse() {
  if (blueprintNodes.value.length || !props.nodes.length) return
  blueprintDraft.value.nodes = props.nodes
    .filter(node => node.node_level <= 2)
    .map(node => ({
      node_id: node.node_id,
      parent_node_id: node.parent_node_id,
      node_name: node.node_name,
      node_level: node.node_level,
      learning_objective: node.learning_objective || '',
      learning_path_role: node.learning_path_role,
      path_reason: node.path_reason,
    }))
}

function syncNavigationFromDraft() {
  if (courseStore.currentCourseId !== props.courseId || !blueprintNodes.value.length) return
  courseStore.applyGenerationOutlineDraft(blueprintNodes.value)
}

async function loadBlueprint() {
  if (!props.courseId || loading.value) return
  loading.value = true
  loadError.value = ''
  actionError.value = ''
  try {
    const data = await workspace.loadBlueprint(props.courseId)
    retrievalArtifact.value = clone(data.retrieval || {})
    coverageArtifact.value = clone(data.coverage || {})
    qualityArtifact.value = clone(
      data.quality
      || data.draft?.course_outline_quality_report
      || data.current?.course_outline_quality_report
      || {},
    )
    blueprintDraft.value = clone(data.draft || data.current || data || {})
    seedNodesFromCourse()
    if (!blueprintDraft.value.course_name) blueprintDraft.value.course_name = props.courseName
    syncNavigationFromDraft()
    baseline.value = draftSignature.value
    adjustmentProposal.value = null
    proposalNotice.value = ''
  } catch {
    loadError.value = t('courseGeneration.gate.loadFailed', '当前确认内容读取失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

function draftPayload(
  source: Record<string, any> = blueprintDraft.value,
  expectedDraftRevisionId?: string,
  proposalId?: string,
  adjustmentOperations?: Record<string, any>[],
) {
  const draft = source
  return {
    base_blueprint_revision_id: draft.base_blueprint_revision_id,
    expected_draft_revision_id: expectedDraftRevisionId || draft.draft_revision_id,
    adjustment_proposal_id: proposalId,
    adjustment_operations: adjustmentOperations,
    course_name: draft.course_name,
    course_purpose: draft.course_purpose,
    course_type: draft.course_type,
    course_intent: draft.course_intent,
    learner_starting_profile: draft.learner_starting_profile,
    course_blueprint: draft.course_blueprint,
    nodes: draft.nodes,
    learning_asset_plan: draft.learning_asset_plan,
    blueprint_locks: draft.blueprint_locks || {},
  }
}

async function persistDraft(showMessage = true) {
  if (!blueprintNodes.value.length) return
  const result = await workspace.saveBlueprint(props.courseId, draftPayload())
  if (result?.draft) blueprintDraft.value = clone(result.draft)
  qualityArtifact.value = clone(result?.quality_report || result?.draft?.course_outline_quality_report || {})
  syncNavigationFromDraft()
  baseline.value = draftSignature.value
  if (showMessage) ElMessage.success(t('courseGeneration.outlineReview.savedMessage', '目录修改已保存'))
}

function safeExternalUrl(value: unknown) {
  try {
    const parsed = new URL(String(value || ''))
    return parsed.protocol === 'https:' ? parsed.toString() : ''
  } catch {
    return ''
  }
}

async function retryRetrieval() {
  if (!props.courseId || retryingRetrieval.value) return
  retryingRetrieval.value = true
  actionError.value = ''
  try {
    const result = await workspace.retryBlueprintRetrieval(props.courseId)
    retrievalArtifact.value = clone(result.retrieval || {})
    const candidate = retrievalArtifact.value?.proposal?.candidate_draft
    if (candidate) {
      blueprintDraft.value = clone(candidate)
      baseline.value = draftSignature.value
      syncNavigationFromDraft()
    }
  } catch (error: any) {
    actionError.value = error?.response?.data?.detail?.message || t(
      'courseGeneration.outlineReview.retrievalRetryFailed',
      '联网核验重试失败，当前本地蓝图仍然保留。',
    )
  } finally {
    retryingRetrieval.value = false
  }
}

function requestId() {
  return `outline-adjustment-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function shapeSummary(shape: Record<string, any> | undefined) {
  const chapters = Number(shape?.chapter_count || 0)
  const sections = Number(shape?.section_count || 0)
  return t('courseGeneration.outlineReview.shapeSummary', '{chapters} 章 · {sections} 节')
    .replace('{chapters}', String(chapters))
    .replace('{sections}', String(sections))
}

function changedFieldSummary(changes: Record<string, any> | undefined) {
  const labels: Record<string, string> = {
    node_name: t('courseGeneration.outlineReview.changedName', '标题'),
    learning_objective: t('courseGeneration.outlineReview.changedObjective', '学习目标'),
    scope_boundary: t('courseGeneration.outlineReview.changedScopeBoundary', '范围边界'),
    assessment: t('courseGeneration.outlineReview.changedAssessment', '达成检验'),
    prerequisite_node_ids: t('courseGeneration.outlineReview.changedDependencies', '前置依赖'),
  }
  return Object.keys(changes || {}).map(field => labels[field] || field).join('、')
}

function proposalFitsNodeTarget(proposal: Record<string, any>, nodeId: string) {
  const operations = Array.isArray(proposal.operations) ? proposal.operations : []
  if (!operations.length) return false
  return operations.every((operation: Record<string, any>) => (
    String(operation.op || '') === 'update_node'
    && String(operation.node_ref || '') === nodeId
  ))
}

function nodeProposalChanges(nodeId: string) {
  const updated = (adjustmentProposal.value?.diff?.updated || []).find(
    (item: Record<string, any>) => String(item.node_id || '') === nodeId,
  )
  const labels: Record<string, string> = {
    node_name: t('courseTasks.blueprint.nodeName', '章节名称'),
    learning_objective: t('courseTasks.blueprint.objective', '学习目标'),
    scope_boundary: t('courseGeneration.outlineReview.scopeBoundary', '内容边界'),
    assessment: t('courseGeneration.outlineReview.assessmentLabel', '达成检验'),
    prerequisite_node_ids: t('courseGeneration.outlineReview.changedDependencies', '前置依赖'),
  }
  return Object.entries(updated?.changes || {}).map(([field, values]: [string, any]) => ({
    field,
    label: labels[field] || field,
    before: values?.before,
    after: values?.after,
  }))
}

function proposalValue(value: unknown) {
  if (Array.isArray(value)) return value.length ? value.join('、') : '—'
  const text = String(value ?? '').trim()
  return text || '—'
}

function outlineNodeId(prefix: string) {
  const suffix = typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}-${suffix}`
}

function markManualChange(message: string) {
  invalidateProposal()
  proposalNotice.value = message
  liveStatus.value = message
}

function selectOutlineNode(node: Record<string, any>) {
  selectedNodeId.value = String(node?.node_id || '')
}

function openNodeAi(node: Record<string, any>) {
  if (adjustmentBusy.value || adjustmentProposal.value) return
  const nodeId = String(node?.node_id || '')
  if (!nodeId) return
  selectedNodeId.value = nodeId
  aiTargetNodeId.value = nodeId
  nodeAiInstruction.value = ''
  liveStatus.value = t('courseGeneration.outlineReview.aiNodeReady', '已选中当前内容，可直接提出修改要求')
}

function scopedNodeInstruction(node: Record<string, any>, instruction: string) {
  const nodeId = String(node?.node_id || '')
  const nodeName = String(node?.node_name || '').trim()
  return [
    `仅允许修改大纲节点「${nodeName}」（节点 ID：${nodeId}）。`,
    '不得新增、删除、移动或修改其他节点；保留当前课程的知识边界和前置关系。',
    instruction,
  ].join('\n')
}

async function runNodeAi(node: Record<string, any>) {
  const instruction = nodeAiInstruction.value.trim()
  if (!instruction || adjustmentBusy.value || adjustmentProposal.value) return
  const nodeId = String(node?.node_id || '')
  if (!nodeId) return
  selectedNodeId.value = nodeId
  aiTargetNodeId.value = nodeId
  adjustmentInstruction.value = scopedNodeInstruction(node, instruction)
  await generateAdjustmentProposal()
}

async function runNodeAiPreset(node: Record<string, any>, instruction: string) {
  nodeAiInstruction.value = instruction
  await runNodeAi(node)
}

async function focusOutlineNode(nodeId: string) {
  await nextTick()
  const chapterInput = Array.from(
    chaptersRef.value?.querySelectorAll<HTMLInputElement>('[data-outline-node-id]') || [],
  ).find(input => input.dataset.outlineNodeId === nodeId)
  if (!chapterInput) return
  if (typeof chapterInput.scrollIntoView === 'function') {
    chapterInput.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  chapterInput.focus({ preventScroll: true })
  chapterInput.select()
}

async function addChapter() {
  const chapterCount = blueprintNodes.value.filter(node => Number(node.node_level || 2) === 1).length
  const nodeId = outlineNodeId('chapter')
  blueprintNodes.value.push({
    node_id: nodeId,
    parent_node_id: 'root',
    node_name: t('courseGeneration.outlineReview.newChapterName', '新章节 {number}').replace('{number}', String(chapterCount + 1)),
    node_level: 1,
    learning_objective: '',
    prerequisite_node_ids: [],
  })
  markManualChange(t('courseGeneration.outlineReview.manualChanged', '目录已修改，保存后生效'))
  await focusOutlineNode(nodeId)
}

async function addSection(chapter: any) {
  const parentId = String(chapter?.node_id || '')
  if (!parentId) return
  const siblings = blueprintNodes.value.filter(node => String(node.parent_node_id || '') === parentId)
  const chapterIndex = blueprintNodes.value.indexOf(chapter)
  let insertAt = chapterIndex + 1
  while (insertAt < blueprintNodes.value.length && Number(blueprintNodes.value[insertAt]?.node_level || 2) !== 1) insertAt += 1
  const nodeId = outlineNodeId('section')
  blueprintNodes.value.splice(insertAt, 0, {
    node_id: nodeId,
    parent_node_id: parentId,
    node_name: t('courseGeneration.outlineReview.newSectionName', '新小节 {number}').replace('{number}', String(siblings.length + 1)),
    node_level: 2,
    learning_objective: '',
    prerequisite_node_ids: [],
  })
  markManualChange(t('courseGeneration.outlineReview.manualChanged', '目录已修改，保存后生效'))
  await focusOutlineNode(nodeId)
}

function siblingNodes(node: any) {
  const level = Number(node?.node_level || 2)
  return blueprintNodes.value.filter(candidate => level === 1
    ? Number(candidate.node_level || 2) === 1
    : Number(candidate.node_level || 2) !== 1 && String(candidate.parent_node_id || '') === String(node.parent_node_id || ''))
}

function canMoveNode(node: any, direction: -1 | 1) {
  const siblings = siblingNodes(node)
  const index = siblings.indexOf(node)
  return direction < 0 ? index > 0 : index >= 0 && index < siblings.length - 1
}

function moveOutlineNode(node: any, direction: -1 | 1) {
  if (!canMoveNode(node, direction)) return
  if (Number(node.node_level || 2) !== 1) {
    const siblings = siblingNodes(node)
    const target = siblings[siblings.indexOf(node) + direction]
    const sourceIndex = blueprintNodes.value.indexOf(node)
    const targetIndex = blueprintNodes.value.indexOf(target)
    blueprintNodes.value.splice(sourceIndex, 1)
    blueprintNodes.value.splice(targetIndex, 0, node)
  } else {
    const chapters = siblingNodes(node)
    const target = chapters[chapters.indexOf(node) + direction]
    const blockFor = (chapter: any) => blueprintNodes.value.filter(candidate => candidate === chapter || String(candidate.parent_node_id || '') === String(chapter.node_id || ''))
    const blocks = chapters.map(blockFor)
    const sourceBlockIndex = chapters.indexOf(node)
    const targetBlockIndex = chapters.indexOf(target)
    const sourceBlock = blocks[sourceBlockIndex]!
    const targetBlock = blocks[targetBlockIndex]!
    blocks[sourceBlockIndex] = targetBlock
    blocks[targetBlockIndex] = sourceBlock
    const chapterIds = new Set(chapters.flatMap(chapter => blockFor(chapter).map(item => item.node_id)))
    const untouched = blueprintNodes.value.filter(candidate => !chapterIds.has(candidate.node_id))
    blueprintNodes.value.splice(0, blueprintNodes.value.length, ...blocks.flat(), ...untouched)
  }
  markManualChange(t('courseGeneration.outlineReview.manualChanged', '目录已修改，保存后生效'))
}

function removeOutlineNode(node: any) {
  const removedIds = new Set<string>([String(node.node_id || '')])
  if (Number(node.node_level || 2) === 1) {
    blueprintNodes.value.forEach(candidate => {
      if (String(candidate.parent_node_id || '') === String(node.node_id || '')) removedIds.add(String(candidate.node_id || ''))
    })
  }
  const kept = blueprintNodes.value.filter(candidate => !removedIds.has(String(candidate.node_id || '')))
  kept.forEach(candidate => {
    if (Array.isArray(candidate.prerequisite_node_ids)) {
      candidate.prerequisite_node_ids = candidate.prerequisite_node_ids.filter((id: string) => !removedIds.has(String(id)))
    }
  })
  blueprintNodes.value.splice(0, blueprintNodes.value.length, ...kept)
  markManualChange(t('courseGeneration.outlineReview.manualChanged', '目录已修改，保存后生效'))
}

function invalidateProposal() {
  if (!adjustmentProposal.value) return
  adjustmentProposal.value = null
  emit('ai-candidate-change', null)
  proposalNotice.value = t(
    'courseGeneration.outlineReview.proposalInvalidated',
    '目录已被手动修改，请重新生成方案',
  )
  liveStatus.value = proposalNotice.value
}

function outlineAdjustmentFailureMessage(error: any) {
  const status = Number(error?.response?.status || 0)
  const code = String(error?.response?.data?.detail?.code || '')
  if (code === 'outline_adjustment_lifecycle_conflict') {
    return t(
      'courseGeneration.outlineReview.proposalLifecycleConflict',
      '当前大纲不在可调整阶段，请重新进入编辑后再试。',
    )
  }
  if (status === 409) {
    return t('courseGeneration.outlineReview.proposalConflict', '目录版本已变化，请重新载入后生成方案。')
  }
  if (status === 503) {
    return t('courseGeneration.outlineReview.proposalUnavailable', 'AI 调整服务暂时不可用，请稍后重试。')
  }
  return t('courseGeneration.outlineReview.proposalFailed', '调整方案生成失败，请换一种说法后重试。')
}

async function generateAdjustmentProposal() {
  const instruction = adjustmentInstruction.value.trim()
  if (!instruction || acting.value || !blueprintNodes.value.length) return null
  generatingProposal.value = true
  adjustmentProposal.value = null
  proposalNotice.value = ''
  actionError.value = ''
  liveStatus.value = t('courseGeneration.outlineReview.adjustmentGenerating', '正在生成方案')
  try {
    if (dirty.value) await persistDraft(false)
    adjustmentRequestId.value = requestId()
    const proposal = await workspace.previewBlueprintAdjustment(props.courseId, {
      request_id: adjustmentRequestId.value,
      base_blueprint_revision_id: blueprintDraft.value.base_blueprint_revision_id,
      expected_draft_revision_id: blueprintDraft.value.draft_revision_id,
      instruction,
    })
    const candidate = clone(proposal)
    if (aiTargetNodeId.value && !proposalFitsNodeTarget(candidate, aiTargetNodeId.value)) {
      candidate.can_apply = false
      candidate.blocking_issues = [
        ...(Array.isArray(candidate.blocking_issues) ? candidate.blocking_issues : []),
        {
          code: 'outline_node_scope_exceeded',
          message: t('courseGeneration.outlineReview.aiNodeScopeExceeded', 'AI 修改超出当前选区，请调整要求后重新生成。'),
        },
      ]
    }
    adjustmentProposal.value = candidate
    emit('ai-candidate-change', adjustmentProposal.value)
    liveStatus.value = candidate.can_apply
      ? t('courseGeneration.outlineReview.proposalReady', '调整方案已生成，请检查整套差异')
      : t('courseGeneration.outlineReview.proposalBlocked', '调整方案存在阻断项，不能应用')
    await nextTick()
    proposalSummaryRef.value?.focus()
    return adjustmentProposal.value
  } catch (error: any) {
    actionError.value = outlineAdjustmentFailureMessage(error)
    liveStatus.value = actionError.value
    emit('ai-error', actionError.value)
    return null
  } finally {
    generatingProposal.value = false
  }
}

function cancelAdjustmentProposal() {
  const proposalId = String(adjustmentProposal.value?.proposal_id || '')
  if (proposalId && adjustmentRequestId.value) {
    void workspace.cancelBlueprintAdjustment(
      props.courseId,
      proposalId,
      adjustmentRequestId.value,
    ).catch(() => undefined)
  }
  adjustmentProposal.value = null
  emit('ai-candidate-change', null)
  proposalNotice.value = ''
  liveStatus.value = t('courseGeneration.outlineReview.proposalCancelled', '已取消调整方案，目录没有变化')
}

async function applyAdjustmentProposal() {
  const proposal = adjustmentProposal.value
  if (!proposal?.can_apply || acting.value) return false
  applyingProposal.value = true
  actionError.value = ''
  liveStatus.value = t('courseGeneration.outlineReview.proposalApplying', '正在应用')
  try {
    const candidate = clone(proposal.draft || {})
    const result = await workspace.saveBlueprint(
      props.courseId,
      draftPayload(
        candidate,
        proposal.source_draft_revision_id,
        proposal.proposal_id,
        proposal.operations,
      ),
    )
    adjustmentProposal.value = null
    emit('ai-candidate-change', null)
    blueprintDraft.value = clone(result?.draft || candidate)
    qualityArtifact.value = clone(result?.quality_report || result?.draft?.course_outline_quality_report || {})
    syncNavigationFromDraft()
    baseline.value = draftSignature.value
    aiTargetNodeId.value = ''
    nodeAiInstruction.value = ''
    proposalNotice.value = t('courseGeneration.outlineReview.proposalApplied', '方案已应用并保存')
    liveStatus.value = proposalNotice.value
    ElMessage.success(proposalNotice.value)
    return true
  } catch (error: any) {
    const status = Number(error?.response?.status || 0)
    actionError.value = status === 409
      ? t('courseGeneration.outlineReview.proposalConflict', '目录版本已变化，请重新载入后生成方案。')
      : t('courseGeneration.outlineReview.proposalApplyFailed', '方案应用失败，原目录草稿未改变。')
    liveStatus.value = actionError.value
    emit('ai-error', actionError.value)
    return false
  } finally {
    applyingProposal.value = false
  }
}

async function requestAiCandidate(instruction: string) {
  aiTargetNodeId.value = ''
  nodeAiInstruction.value = ''
  adjustmentInstruction.value = instruction.trim()
  return generateAdjustmentProposal()
}

function plainOutlineTitle(value: unknown) {
  return String(value || '')
    .replace(/^\s*第\s*\d+\s*章\s*/, '')
    .replace(/^\s*\d+(?:\.\d+)?\s*/, '')
    .trim()
}

function assessmentItems(value: unknown) {
  if (Array.isArray(value)) {
    return value.map(item => String(item || '').trim()).filter(Boolean)
  }
  const item = String(value || '').trim()
  return item ? [item] : []
}

function qualityIssueLocation(issue: Record<string, any>) {
  const ids = Array.isArray(issue.node_ids) ? issue.node_ids.map(item => String(item)) : []
  const names = ids.map(nodeId => {
    const node = blueprintNodes.value.find(item => String(item.node_id || '') === nodeId)
    return plainOutlineTitle(node?.node_name || nodeId)
  }).filter(Boolean)
  if (!names.length) return t('courseGeneration.outlineReview.qualityWholeDocument', '整篇大纲')
  const visible = names.slice(0, 3).join('、')
  return names.length > 3
    ? t('courseGeneration.outlineReview.qualityLocationsMore', '{names} 等 {count} 节')
      .replace('{names}', visible)
      .replace('{count}', String(names.length))
    : visible
}

function qualityIssueActionable(issue: Record<string, any>) {
  return Boolean(
    props.requiresConfirmation
    && String(issue.repair_instruction || '').trim()
    && Array.isArray(issue.node_ids)
    && issue.node_ids.length,
  )
}

async function repairQualityIssue(issue: Record<string, any>) {
  const baseInstruction = String(issue.repair_instruction || '').trim()
  const nodeIds = Array.isArray(issue.node_ids)
    ? issue.node_ids.map((item: unknown) => String(item || '').trim()).filter(Boolean)
    : []
  const instruction = nodeIds.length
    ? `${baseInstruction}\n仅允许修改节点：${nodeIds.join('、')}。`
    : baseInstruction
  if (!instruction || adjustmentBusy.value) return
  repairingQualityCode.value = String(issue.code || '')
  aiTargetNodeId.value = ''
  nodeAiInstruction.value = ''
  adjustmentInstruction.value = instruction
  emit('open-ai')
  await nextTick()
  await generateAdjustmentProposal()
  repairingQualityCode.value = ''
}

async function resolveAiCandidate(accept: boolean) {
  if (!adjustmentProposal.value || adjustmentBusy.value) return false
  emit('ai-resolving', { accept })
  const resolved = accept ? await applyAdjustmentProposal() : (cancelAdjustmentProposal(), true)
  if (resolved) emit('ai-resolved', { accept })
  return resolved
}

async function focusAiCandidate() {
  await nextTick()
  proposalSummaryRef.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  proposalSummaryRef.value?.focus({ preventScroll: true })
}

async function saveDraft() {
  if (!dirty.value || acting.value) return
  saving.value = true
  actionError.value = ''
  try {
    await persistDraft()
  } catch {
    actionError.value = t('courseGeneration.outlineReview.saveFailed', '目录修改保存失败，请检查后重试。')
  } finally {
    saving.value = false
  }
}

async function finishEditing() {
  if (acting.value) return false
  if (!dirty.value) return true
  saving.value = true
  actionError.value = ''
  try {
    await persistDraft()
    return true
  } catch {
    actionError.value = t('courseGeneration.outlineReview.saveFailed', '目录修改保存失败，请检查后重试。')
    return false
  } finally {
    saving.value = false
  }
}

async function confirmOutline() {
  if (!blueprintNodes.value.length || acting.value) return
  confirming.value = true
  actionError.value = ''
  try {
    if (dirty.value) await persistDraft(false)
    await workspace.confirmGenerationStep(props.courseId, 'outline')
    generationStore.startGlobalMonitor()
    if (props.surface === 'teacher') {
      await courseStore.refreshGenerationPreview(props.courseId, 'teacher')
      ElMessage.success(t('courseWorkbench.outlineConfirmed', '大纲已确认'))
    } else {
      await courseStore.refreshCourseData(props.courseId)
      ElMessage.success(t('courseGeneration.gate.confirmed', '已确认，课程继续生成'))
    }
    emit('confirmed')
  } catch {
    actionError.value = t('courseGeneration.gate.confirmFailed', '确认失败，请检查目录后重试。')
  } finally {
    confirming.value = false
  }
}

defineExpose({ finishEditing, requestAiCandidate, resolveAiCandidate, focusAiCandidate })
</script>

<style scoped>
.outline-review {
  box-sizing:border-box;
  height:100%;
  min-height:0;
  flex:1;
  display:flex;
  overflow:hidden;
  padding:0 clamp(24px,4vw,64px);
  background:#fff;
}
.outline-review__sheet {
  width:min(1280px,100%);
  height:100%;
  min-height:0;
  display:grid;
  grid-template-rows:minmax(0,1fr) auto;
  margin:0 auto;
  overflow:hidden;
  background:#fff;
}
.outline-review__loading,
.outline-review__load-error {
  grid-row:1;
  min-height:260px;
  display:flex;
  align-items:center;
  justify-content:center;
  gap:9px;
  padding:30px;
  color:#687386;
  font-size:13px;
}
.outline-review__loading svg {
  color:#4f46d9;
  animation:outline-review-spin .9s linear infinite;
}
.outline-review__load-error {
  min-height:150px;
  color:#9a4d13;
}
.outline-review__load-error > div { max-width:520px; }
.outline-review__load-error p { margin:4px 0 0; color:#84664c; font-size:12px; }
.outline-review__load-error button {
  min-height:38px;
  padding:0 14px;
  border:1px solid #e2a753;
  border-radius:7px;
  color:#9a4d13;
  background:#fffaf0;
  font-size:12px;
  font-weight:800;
  cursor:pointer;
}
.outline-review__body {
  min-height:0;
  overflow:auto;
  overscroll-behavior:contain;
  scrollbar-gutter:stable;
  scrollbar-color:#c9ced8 transparent;
}
.outline-review__setup {
  min-width:0;
  border-bottom:1px solid #eceef2;
}
.outline-review__setup > :first-child { border-top:0; }
.outline-review input,
.outline-review textarea {
  width:100%;
  border:1px solid transparent;
  border-radius:7px;
  color:#273144;
  background:transparent;
  outline:none;
  transition:border-color .16s ease,background .16s ease,box-shadow .16s ease;
}
.outline-review input:hover,
.outline-review textarea:hover { background:#f8f9fb; }
.outline-review input:focus,
.outline-review textarea:focus {
  border-color:#aeb4e9;
  background:#fff;
  box-shadow:0 0 0 3px rgba(79,70,217,.08);
}
.outline-review__starting-point {
  margin:0;
  padding:16px 0 18px 114px;
  border-top:1px solid #eceef2;
}
.outline-review__starting-point > header {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-bottom:10px;
}
.outline-review__starting-point > header span {
  color:#344054;
  font-size:12px;
  font-weight:800;
}
.outline-review__starting-point > header strong {
  padding:0;
  color:#087a5b;
  font-size:12px;
}
.outline-review__starting-point[data-status="insufficient"] > header strong {
  color:#9a5b17;
}
.outline-review__starting-point > div {
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:16px;
}
.outline-review__starting-point p { min-width:0; margin:0; }
.outline-review__starting-point small {
  display:block;
  margin-bottom:3px;
  color:#8a93a3;
  font-size:12px;
  font-weight:750;
}
.outline-review__starting-point p span {
  display:block;
  overflow-wrap:anywhere;
  color:#455166;
  font-size:12px;
  line-height:1.5;
}
.outline-review__starting-point > footer {
  margin-top:9px;
  color:#7b8494;
  font-size:10px;
  line-height:1.5;
}
.outline-coverage { margin:14px 30px 2px; border:1px solid #fed7aa; border-radius:12px; padding:13px; background:linear-gradient(135deg,#fff7ed,#fffbf5); }
.outline-coverage[data-status="complete"] { border-color:#bbf7d0; background:linear-gradient(135deg,#f0fdf4,#fafffb); }
.outline-coverage > header { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.outline-coverage > header strong { color:#9a3412; font-size:13px; }
.outline-coverage[data-status="complete"] > header strong { color:#166534; }
.outline-coverage > header small { border-radius:999px; padding:3px 7px; color:#9a3412; background:#ffedd5; font-size:9px; white-space:nowrap; }
.outline-coverage[data-status="complete"] > header small { color:#166534; background:#dcfce7; }
.outline-coverage > p { margin:9px 0 0; color:#475569; font-size:11px; line-height:1.55; }
.outline-coverage__uncovered { margin-top:10px; border-radius:8px; padding:8px; background:rgba(255,255,255,.75); }
.outline-coverage__uncovered > span { color:#9a3412; font-size:9px; }
.outline-coverage__uncovered ul { display:flex; flex-wrap:wrap; gap:4px 6px; margin:5px 0 0; padding:0; list-style:none; }
.outline-coverage__uncovered li { border:1px solid #fed7aa; border-radius:999px; padding:2px 7px; color:#7c2d12; background:#fff; font-size:10px; }
.outline-coverage__advisories { margin:9px 0 0; padding-left:15px; }
.outline-coverage__advisories li { color:#7c2d12; font-size:10px; line-height:1.5; }
.outline-retrieval { margin:0; padding:18px 0 20px 114px; border-top:1px solid #eceef2; }
.outline-retrieval > header { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.outline-retrieval > header div { display:grid; gap:2px; }
.outline-retrieval > header strong { color:#312e81; font-size:14px; }
.outline-retrieval > header small,.outline-retrieval > header > span { color:#6366f1; font-size:12px; }
.outline-retrieval > header > span { padding:2px 0; white-space:nowrap; }
.outline-retrieval > p { max-width:880px; margin:10px 0; color:#475569; font-size:13px; line-height:1.65; }
.outline-retrieval__shape { display:flex; align-items:center; gap:7px; color:#4338ca; font-size:12px; }
.outline-retrieval__diff { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:0; margin-top:14px; border-top:1px solid #e4e7f5; border-bottom:1px solid #e4e7f5; }
.outline-retrieval__diff section { min-width:0; padding:12px 18px 13px 0; }
.outline-retrieval__diff section + section { padding-left:18px; border-left:1px solid #e4e7f5; }
.outline-retrieval__diff h3 { margin:0 0 7px; color:#475569; font-size:12px; }
.outline-retrieval__diff ul { margin:0; padding-left:17px; }
.outline-retrieval__diff li { margin:4px 0; color:#334155; font-size:12px; line-height:1.5; }
.outline-retrieval__diff li small { display:block; color:#64748b; font-size:12px; }
.outline-retrieval__sources { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:0; margin-top:14px; border-top:1px solid #e4e7f5; }
.outline-retrieval__source { min-width:0; display:grid; gap:3px; padding:11px 14px 0 0; color:#3730a3; text-decoration:none; }
.outline-retrieval__source + .outline-retrieval__source { padding-left:14px; border-left:1px solid #e4e7f5; }
.outline-retrieval__source:hover strong { text-decoration:underline; }
.outline-retrieval__source strong { overflow:hidden; font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.outline-retrieval__source small { color:#64748b; font-size:12px; }
.outline-retrieval--notice { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:10px; }
.outline-retrieval--notice strong { color:#9a3412; font-size:13px; }
.outline-retrieval--notice p { margin:2px 0 0; color:#9a3412; font-size:12px; }
.outline-retrieval--notice .outline-retrieval__stats { color:#7c2d12; font-size:12px; }
.outline-retrieval--notice button { border:1px solid #fdba74; border-radius:8px; padding:6px 9px; color:#9a3412; background:#fff; font-size:12px; cursor:pointer; }
.outline-retrieval--notice > small { grid-column:1/-1; color:#7c2d12; font-size:12px; }
.outline-review__adjustment {
  display:grid;
  grid-template-columns:140px minmax(280px,1fr) auto;
  align-items:center;
  gap:14px;
  margin:0;
  padding:16px 0;
  border-top:1px solid #eceef2;
}
.outline-review__adjustment label {
  color:#344054;
  font-size:12px;
  font-weight:850;
}
.outline-review__adjustment-heading { display:flex; align-items:center; }
.outline-review__adjustment textarea {
  min-height:56px;
  padding:9px 11px;
  border-color:#d9ddea;
  background:#fbfbfe;
  resize:vertical;
  font-size:12px;
  line-height:1.5;
}
.outline-review__adjustment button,
.outline-review__proposal-actions button {
  min-height:39px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:6px;
  padding:0 13px;
  border:1px solid #c9cdea;
  border-radius:8px;
  color:#454ca8;
  background:#f7f7ff;
  font-size:12px;
  font-weight:800;
  cursor:pointer;
}
.outline-review__adjustment button:disabled,
.outline-review__proposal-actions button:disabled { opacity:.5; cursor:not-allowed; }
.outline-review__adjustment svg.lucide-loader-circle,
.outline-review__proposal-actions svg.lucide-loader-circle { animation:outline-review-spin .9s linear infinite; }
.outline-review__proposal-notice {
  margin:0;
  padding:7px 0 10px 114px;
  color:#087a5b;
  font-size:12px;
  font-weight:750;
}
.outline-review__proposal {
  margin:0 0 16px 114px;
  border:1px solid #d9dcef;
  border-radius:10px;
  background:#fbfbff;
  outline:none;
}
.outline-review__proposal:focus { box-shadow:0 0 0 3px rgba(79,70,217,.1); }
.outline-review__proposal details { padding:10px 12px 12px; }
.outline-review__proposal summary {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
  color:#343b86;
  font-size:12px;
  font-weight:850;
  cursor:pointer;
}
.outline-review__proposal summary strong {
  display:inline-flex;
  align-items:center;
  gap:5px;
  color:#60687b;
  font-size:12px;
}
.outline-review__proposal-summary {
  margin:9px 0;
  color:#3e485b;
  font-size:12px;
  line-height:1.55;
}
.outline-review__diff-groups {
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:8px;
}
.outline-review__diff-groups section {
  min-width:0;
  padding:10px 14px 10px 0;
  border-top:1px solid #e5e7ef;
}
.outline-review__diff-groups section + section { padding-left:14px; border-left:1px solid #e5e7ef; }
.outline-review__diff-groups h3 { margin:0 0 5px; color:#596579; font-size:12px; }
.outline-review__diff-groups ul,
.outline-review__blockers { margin:0; padding-left:16px; }
.outline-review__diff-groups li { margin:3px 0; color:#344054; font-size:12px; }
.outline-review__diff-groups li span,
.outline-review__diff-groups li small { display:block; overflow-wrap:anywhere; }
.outline-review__diff-groups li small { margin-top:1px; color:#7b8494; font-size:12px; }
.outline-review__blockers {
  margin-top:9px;
  color:#b42318;
  font-size:12px;
}
.outline-review__proposal-actions {
  display:flex;
  justify-content:flex-end;
  gap:7px;
  margin-top:10px;
}
.outline-review__proposal-actions button.primary {
  border-color:#454ca8;
  color:#fff;
  background:#454ca8;
}
.outline-review__sr-only {
  position:absolute;
  width:1px;
  height:1px;
  overflow:hidden;
  clip:rect(0,0,0,0);
  white-space:nowrap;
}
.outline-view-switch {
  position:sticky;
  z-index:5;
  top:0;
  display:flex;
  justify-content:flex-end;
  gap:3px;
  padding:14px 0 8px;
  background:rgba(255,255,255,.94);
  backdrop-filter:saturate(135%) blur(10px);
}
.outline-view-switch button {
  min-height:34px;
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:0 11px;
  border:1px solid transparent;
  border-radius:8px;
  color:#697386;
  background:transparent;
  font-size:12px;
  font-weight:750;
  cursor:pointer;
  transition:color .18s ease,background .18s ease,border-color .18s ease;
}
.outline-view-switch button:hover { color:#3f47a8; background:#f7f7ff; }
.outline-view-switch button:focus-visible { outline:3px solid rgba(79,70,217,.14); outline-offset:1px; }
.outline-view-switch button.active { border-color:#d9dcf3; color:#3f47a8; background:#f4f4ff; }
.formal-outline {
  width:min(980px,100%);
  margin:0 auto;
  padding:0 0 56px;
  color:#20293a;
  animation:formal-outline-reveal .42s cubic-bezier(.16,1,.3,1) both;
}
.formal-outline__masthead {
  position:relative;
  overflow:hidden;
  padding:42px clamp(34px,6vw,70px) 30px;
  border:1px solid #e5e6f4;
  border-radius:16px;
  background:linear-gradient(145deg,#f7f7ff 0%,#fff 62%);
  box-shadow:0 18px 44px rgba(32,38,89,.08);
}
.formal-outline__masthead::after {
  content:"";
  position:absolute;
  top:-58px;
  right:-34px;
  width:180px;
  height:180px;
  border-radius:50%;
  background:radial-gradient(circle,rgba(99,102,241,.12),rgba(99,102,241,0) 70%);
  pointer-events:none;
}
.formal-outline__kicker {
  display:flex;
  align-items:center;
  gap:7px;
  color:#4f55b5;
  font-size:12px;
  font-weight:800;
}
.formal-outline__masthead h1 {
  max-width:18ch;
  margin:14px 0 10px;
  color:#171d31;
  font-size:clamp(28px,3.2vw,40px);
  line-height:1.15;
  letter-spacing:-.025em;
  text-wrap:balance;
}
.formal-outline__masthead > p {
  max-width:68ch;
  margin:0;
  color:#596579;
  font-size:14px;
  line-height:1.75;
}
.formal-outline__masthead dl {
  display:flex;
  flex-wrap:wrap;
  gap:24px;
  margin:28px 0 0;
}
.formal-outline__masthead dl div { display:flex; align-items:baseline; gap:8px; }
.formal-outline__masthead dt { color:#81899a; font-size:11px; }
.formal-outline__masthead dd { margin:0; color:#303a50; font-size:13px; font-weight:800; }
.formal-outline__masthead dd[data-ready="true"] { color:#087a5b; }
.formal-outline__masthead dd[data-ready="false"] { color:#9a5b17; }
.formal-outline__brief {
  display:grid;
  grid-template-columns:minmax(0,1.25fr) minmax(240px,.75fr);
  gap:0;
  padding:42px clamp(18px,4vw,44px) 38px;
  border-bottom:1px solid #e7e9ef;
}
.formal-outline__brief > div { min-width:0; padding-right:42px; }
.formal-outline__brief > div + div { padding:0 0 0 42px; border-left:1px solid #e7e9ef; }
.formal-outline__brief h2,
.formal-outline__schedule > header h2,
.outline-quality h2 { margin:0; color:#242d40; font-size:18px; line-height:1.35; letter-spacing:-.012em; }
.formal-outline__brief ol,
.formal-outline__brief ul { margin:15px 0 0; padding-left:22px; }
.formal-outline__brief li { margin:9px 0; padding-left:5px; color:#4f596d; font-size:13px; line-height:1.7; }
.formal-outline__brief > div > p { margin:15px 0 0; color:#737d8f; font-size:13px; line-height:1.7; }
.outline-quality {
  margin:38px clamp(18px,4vw,44px) 8px;
  padding:24px 0 12px;
  border-top:1px solid #dfe1f1;
  border-bottom:1px solid #dfe1f1;
}
.outline-quality > header { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; }
.outline-quality > header span,
.formal-outline__schedule > header span {
  display:block;
  margin-bottom:5px;
  color:#565db4;
  font-size:11px;
  font-weight:800;
}
.outline-quality > header > p { max-width:340px; margin:0; color:#717a8c; font-size:12px; line-height:1.6; text-align:right; }
.outline-quality ol { margin:18px 0 0; padding:0; list-style:none; }
.outline-quality li {
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  align-items:center;
  gap:18px;
  padding:13px 0;
  border-top:1px solid #eff0f5;
}
.outline-quality li strong { display:block; color:#3b4559; font-size:12px; line-height:1.55; }
.outline-quality li small { display:block; margin-top:3px; color:#8a93a3; font-size:11px; }
.outline-quality li button {
  min-height:32px;
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:0 10px;
  border:1px solid #d8daf0;
  border-radius:8px;
  color:#454ca8;
  background:#f8f8ff;
  font-size:11px;
  font-weight:800;
  cursor:pointer;
}
.outline-quality li button:hover:not(:disabled) { border-color:#bfc3e8; background:#f1f1ff; }
.outline-quality li button:focus-visible { outline:3px solid rgba(79,70,217,.14); outline-offset:1px; }
.outline-quality li button:disabled { opacity:.48; cursor:not-allowed; }
.outline-quality li button svg.lucide-loader-circle { animation:outline-review-spin .9s linear infinite; }
.outline-quality > footer { padding:9px 0 0; color:#7d8696; font-size:11px; line-height:1.5; }
.formal-outline__schedule { padding:48px clamp(18px,4vw,44px) 0; }
.formal-outline__schedule > header { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; margin-bottom:14px; }
.formal-outline__schedule > header p { max-width:360px; margin:0; color:#727c8e; font-size:12px; line-height:1.6; text-align:right; }
.formal-outline__chapter-block { border-top:1px solid #dfe3e9; }
.formal-outline__chapter-block > header {
  display:grid;
  grid-template-columns:42px minmax(0,1fr) auto;
  align-items:start;
  gap:16px;
  padding:26px 0 20px;
}
.formal-outline__chapter-block > header > span { color:#6068bd; font-size:12px; font-weight:850; }
.formal-outline__chapter-block h3 { margin:0; color:#1d2639; font-size:20px; line-height:1.35; letter-spacing:-.015em; }
.formal-outline__chapter-block > header p { max-width:70ch; margin:6px 0 0; color:#707a8d; font-size:12px; line-height:1.6; }
.formal-outline__chapter-block > header small { color:#8991a0; font-size:11px; white-space:nowrap; }
.formal-outline__chapter-block > ol { margin:0 0 30px 58px; padding:0; list-style:none; }
.formal-outline__chapter-block > ol > li {
  display:grid;
  grid-template-columns:54px minmax(0,1fr);
  gap:16px;
  padding:18px 0;
  border-top:1px solid #edf0f4;
}
.formal-outline__chapter-block > ol > li > span { padding-top:2px; color:#7a83a5; font-size:12px; font-weight:800; }
.formal-outline__chapter-block h4 { margin:0; color:#2c364b; font-size:15px; line-height:1.45; }
.formal-outline__chapter-block li p { max-width:72ch; margin:6px 0 0; color:#606b7e; font-size:12px; line-height:1.65; }
.formal-outline__chapter-block li p.formal-outline__boundary { color:#8790a0; }
.formal-outline__assessment { display:flex; align-items:flex-start; gap:9px; margin-top:9px; }
.formal-outline__assessment strong { flex:0 0 auto; color:#4f55b5; font-size:11px; }
.formal-outline__assessment span { color:#566175; font-size:11px; line-height:1.6; }
.outline-review__chapters {
  display:grid;
  gap:0;
  min-height:0;
  overflow:visible;
  margin:0;
  padding:24px 0 28px;
}
@keyframes formal-outline-reveal {
  from { opacity:.82; clip-path:inset(0 0 18px 0); transform:translateY(8px); }
  to { opacity:1; clip-path:inset(0); transform:translateY(0); }
}
.outline-review__list-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:50px; border-bottom:1px solid #dfe3e9; }.outline-review__list-toolbar strong { color:#273144; font-size:15px; }.outline-review__list-toolbar button { min-height:34px; display:inline-flex; align-items:center; gap:5px; padding:0 10px; border:1px solid #d9dee7; border-radius:7px; color:#454ca8; background:#fff; font-size:12px; font-weight:700; cursor:pointer; }
.outline-review__chapter {
  min-width:0;
  border-bottom:1px solid #e4e7ec;
}
.outline-review__chapter-heading {
  min-width:0;
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  align-items:start;
  gap:6px 10px;
  padding:18px 8px 16px;
  background:#fff;
}
.outline-review__chapter-heading input {
  height:40px;
  padding:0 8px;
  color:#172033;
  font-size:18px;
  font-weight:800;
}
.outline-review__chapter-heading textarea {
  min-height:36px;
  margin-top:2px;
  padding:7px 8px;
  resize:vertical;
  color:#687386;
  font-size:12px;
  line-height:1.5;
}
.outline-review__section-list {
  margin-left:32px;
}
.outline-review__section {
  min-width:0;
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  align-items:start;
  gap:6px 10px;
  padding:14px 8px 14px 14px;
  border-bottom:1px solid #edf0f4;
}
.outline-review__section:last-child { border-bottom:0; }
.outline-review__chapter--ungrouped .outline-review__section-list { margin-left:0; }
.outline-review__chapter--ungrouped .outline-review__section { padding-left:8px; }
.outline-review__section input {
  height:34px;
  padding:0 8px;
  color:#273144;
  font-size:15px;
  font-weight:750;
}
.outline-review__section textarea {
  min-height:36px;
  margin-top:2px;
  padding:7px 8px;
  resize:vertical;
  color:#687386;
  font-size:12px;
  line-height:1.5;
}
.outline-review__node-fields { min-width:0; display:grid; gap:2px; }.outline-review__node-actions { display:flex; align-items:center; gap:3px; padding-top:4px; }.outline-review__node-actions button { width:28px; height:28px; display:grid; place-items:center; padding:0; border:1px solid transparent; border-radius:7px; color:#687386; background:transparent; cursor:pointer; }.outline-review__node-actions button:hover:not(:disabled),.outline-review__node-actions button:focus-visible { border-color:#d9dee7; color:#454ca8; background:#fff; outline:0; }.outline-review__node-actions button.danger:hover:not(:disabled) { color:#b42318; background:#fff5f5; }.outline-review__node-actions button:disabled { opacity:.3; cursor:not-allowed; }.outline-review__node-actions button.outline-review__node-ai { width:auto; display:inline-flex; gap:5px; padding:0 8px; color:#4f55b5; }.outline-review__node-actions button.outline-review__node-ai span { display:none; font-size:11px; font-weight:750; white-space:nowrap; }.outline-review__chapter.is-selected .outline-review__chapter-heading,.outline-review__section.is-selected { background:#f8f8ff; }.outline-review__chapter.is-selected .outline-review__node-ai span,.outline-review__section.is-selected .outline-review__node-ai span { display:inline; }.outline-review__node-ai-panel { grid-column:1/-1; display:grid; gap:10px; margin:0 14px 14px 54px; padding:12px 0; border-top:1px solid #dfe2f4; border-bottom:1px solid #dfe2f4; background:#fbfbff; }.outline-review__node-ai-quick-actions { display:flex; flex-wrap:wrap; gap:6px; padding:0 12px; }.outline-review__node-ai-quick-actions button,.outline-review__node-proposal-actions button { min-height:30px; display:inline-flex; align-items:center; justify-content:center; gap:5px; padding:0 9px; border:1px solid #d7daed; border-radius:7px; color:#4f55a9; background:#fff; font-size:11px; font-weight:750; cursor:pointer; }.outline-review__node-ai-quick-actions button:disabled,.outline-review__node-proposal-actions button:disabled { opacity:.45; cursor:not-allowed; }.outline-review__node-ai-input { display:grid; grid-template-columns:18px minmax(0,1fr) auto; align-items:center; gap:8px; padding:0 12px; color:#5c5bc3; }.outline-review__node-ai-input input { height:36px; padding:0 8px; border-color:#d7daed; background:#fff; font-size:12px; }.outline-review__node-ai-input > button { min-height:36px; display:inline-flex; align-items:center; gap:5px; padding:0 11px; border:1px solid #5655c6; border-radius:7px; color:#fff; background:#5655c6; font-size:11px; font-weight:800; cursor:pointer; }.outline-review__node-ai-input > button:disabled { opacity:.45; cursor:not-allowed; }.outline-review__node-proposal { display:flex; align-items:center; justify-content:space-between; gap:18px; padding:0 12px; }.outline-review__node-proposal > div:first-child { min-width:0; display:grid; grid-template-columns:18px auto minmax(0,1fr); align-items:start; gap:6px; color:#5655c6; }.outline-review__node-proposal strong { color:#3d448c; font-size:11px; }.outline-review__node-proposal span { color:#5f697b; font-size:11px; line-height:1.5; }.outline-review__node-proposal small { grid-column:2/-1; color:#b42318; font-size:11px; line-height:1.45; }.outline-review__node-proposal-actions { flex:0 0 auto; display:flex; gap:6px; }.outline-review__node-proposal-actions button.primary { border-color:#5655c6; color:#fff; background:#5655c6; }.outline-review__node-meta { grid-column:1/-1; }
.outline-review__node-meta {
  min-width:0;
  display:flex;
  align-items:center;
  gap:8px;
  padding:0 8px 2px;
}
.outline-review__node-proposal {
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  align-items:start;
  gap:10px 18px;
}
.outline-review__node-diff {
  grid-column:1/-1;
  display:grid;
  gap:6px;
  padding:9px 10px;
  border:1px solid #e1e3f1;
  border-radius:8px;
  background:#fff;
}
.outline-review__node-diff>div {
  display:grid;
  grid-template-columns:74px minmax(0,1fr) 16px minmax(0,1fr);
  align-items:start;
  gap:8px;
  color:#7a8495;
  font-size:11px;
  line-height:1.5;
}
.outline-review__node-diff del { color:#8a6470; text-decoration-color:#d8aab5; }
.outline-review__node-diff ins { color:#276749; text-decoration:none; }
.outline-review__node-diff svg { margin-top:2px; color:#9aa3b1; }
.outline-review__node-proposal-actions { grid-column:2; grid-row:1; }
.outline-review__node-meta > span {
  flex:0 0 auto;
  padding:3px 6px;
  border:1px solid #d9dee7;
  border-radius:4px;
  color:#596579;
  background:#f8f9fb;
  font-size:12px;
  font-weight:800;
}
.outline-review__node-meta > span[data-role="focus"] {
  border-color:#e7c790;
  color:#9a5b17;
  background:#fff9ef;
}
.outline-review__node-meta > span[data-role="compressed"] {
  border-color:#bfd7cc;
  color:#087a5b;
  background:#f2faf7;
}
.outline-review__node-meta > span[data-role="verify_in_project"] {
  border-color:#c8c9ed;
  color:#4f55b5;
  background:#f4f4ff;
}
.outline-review__node-meta > span[data-role="milestone"] {
  border-color:#b9c7db;
  color:#35506f;
  background:#f3f7fb;
}
.outline-review__node-meta p {
  min-width:0;
  overflow:hidden;
  margin:0;
  color:#7b8494;
  font-size:12px;
  line-height:1.35;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.outline-review__empty {
  margin:0;
  padding:42px 30px;
  color:#8a93a3;
  text-align:center;
  font-size:13px;
}
.outline-review__footer {
  grid-row:2;
  display:flex;
  align-items:center;
  justify-content:flex-end;
  gap:24px;
  padding:13px 0 14px;
  border-top:1px solid #dfe3e9;
  background:rgba(255,255,255,.98);
}
.outline-review__footer p.outline-review__action-error { min-width:0; margin:0 auto 0 0; color:#b42318; font-size:12px; line-height:1.5; }
.outline-review__actions {
  flex:0 0 auto;
  display:flex;
  align-items:center;
  gap:8px;
}
.outline-review__saved-state {
  min-height:40px;
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:0 8px;
  color:#087a5b;
  font-size:12px;
  font-weight:750;
  white-space:nowrap;
}
.outline-review__actions button {
  min-height:40px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  padding:0 16px;
  border-radius:9px;
  font-size:12px;
  font-weight:800;
  cursor:pointer;
}
.outline-review__actions button:disabled { opacity:.5; cursor:not-allowed; }
.outline-review__actions .secondary {
  border:1px solid #d5dae3;
  color:#596579;
  background:#fff;
}
.outline-review__actions .primary {
  border:1px solid #3f47a8;
  color:#fff;
  background:#3f47a8;
}
.outline-review__actions button:not(:disabled):hover { filter:brightness(.98); }
.outline-review__actions svg.lucide-loader-circle { animation:outline-review-spin .9s linear infinite; }
.outline-review__toolbar-actions { display:flex; align-items:center; gap:7px; margin-left:auto; }

.outline-review[data-variant="inline"] {
  height:auto;
  display:block;
  overflow:visible;
  padding:0;
  background:transparent;
}
.outline-review[data-variant="inline"] .outline-review__sheet {
  width:100%;
  height:auto;
  display:block;
  overflow:visible;
  background:transparent;
}
.outline-review[data-variant="inline"] .outline-review__body { overflow:visible; }
.outline-review[data-variant="inline"] .outline-view-switch { padding:14px 20px 8px; }
.outline-review[data-variant="inline"] .formal-outline { padding-inline:20px; }
.outline-review[data-variant="inline"] .outline-review__loading,
.outline-review[data-variant="inline"] .outline-review__load-error { min-height:180px; }
.outline-review[data-variant="inline"] .outline-review__setup {
  padding:0 20px;
  border-bottom:1px solid #e7ebf2;
}
.outline-review[data-variant="inline"] .outline-review__adjustment {
  grid-template-columns:minmax(0,1fr) auto;
  gap:10px;
  padding:14px 0;
  border:0;
}
.outline-review[data-variant="inline"] .outline-review__adjustment-heading {
  position:absolute;
  width:1px;
  height:1px;
  overflow:hidden;
  clip:rect(0,0,0,0);
  white-space:nowrap;
}
.outline-review[data-variant="inline"] .outline-review__adjustment textarea { min-height:42px; resize:none; }
.outline-review[data-variant="inline"] .outline-review__proposal-notice { padding:0 0 12px; }
.outline-review[data-variant="inline"] .outline-review__proposal { margin:0 0 14px; }
.outline-review[data-variant="inline"] .outline-review__chapters {
  width:min(980px,100%);
  gap:0;
  margin:0 auto;
  padding:30px 32px 38px;
}
.outline-review[data-variant="inline"] .outline-review__list-toolbar {
  min-height:34px;
  justify-content:flex-end;
  margin-bottom:-2px;
  border:0;
}
.outline-review[data-variant="inline"] .outline-review__chapter {
  overflow:visible;
  border:0;
  border-top:1px solid #dfe3e9;
  border-radius:0;
  background:#fff;
}
.outline-review[data-variant="inline"] .outline-review__chapter:first-of-type { border-top:0; }
.outline-review[data-variant="inline"] .outline-review__chapter-heading {
  grid-template-columns:30px minmax(0,1fr) auto;
  align-items:center;
  gap:11px;
  min-height:72px;
  padding:16px 4px 12px;
}
.outline-review[data-variant="inline"] .outline-review__chapter-index {
  width:28px;
  height:28px;
  display:grid;
  place-items:center;
  color:#6366a8;
  background:transparent;
  font-size:10px;
  font-weight:800;
}
.outline-review[data-variant="inline"] .outline-review__chapter-heading input {
  height:28px;
  padding:0;
  color:#263147;
  font-size:13px;
  font-weight:800;
}
.outline-review[data-variant="inline"] .outline-review__chapter-heading textarea {
  min-height:24px;
  margin:0;
  padding:2px 0;
  resize:none;
  color:#64748b;
  font-size:11px;
  line-height:1.45;
}
.outline-review[data-variant="inline"] .outline-review__objective-text {
  min-width:0;
  margin:0;
  color:#64748b;
  font-size:11px;
  line-height:1.55;
  overflow-wrap:anywhere;
  white-space:pre-wrap;
}
.outline-review[data-variant="inline"] .outline-review__section-list { margin:0 0 18px 19px; padding:0 4px 2px 34px; border-left:1px solid #e4e6ef; }
.outline-review[data-variant="inline"] .outline-review__section {
  grid-template-columns:46px minmax(0,1fr) auto;
  align-items:center;
  gap:8px;
  min-height:54px;
  padding:9px 4px;
  border-top:0;
  border-bottom:0;
}
.outline-review[data-variant="inline"] .outline-review__section-index {
  color:#6366f1;
  font-size:11px;
  font-weight:750;
}
.outline-review[data-variant="inline"] .outline-review__section input {
  height:26px;
  padding:0;
  color:#334155;
  font-size:12px;
  font-weight:750;
}
.outline-review[data-variant="inline"] .outline-review__section textarea {
  min-height:22px;
  margin:0;
  padding:1px 0;
  resize:none;
  color:#64748b;
  font-size:11px;
  line-height:1.45;
}
.outline-review[data-variant="inline"].is-editing .outline-review__node-fields textarea {
  field-sizing:content;
  overflow-y:hidden;
}
.outline-review[data-variant="inline"] input[readonly],
.outline-review[data-variant="inline"] textarea[readonly] {
  pointer-events:none;
  cursor:default;
}
.outline-review[data-variant="inline"].is-editing .outline-review__node-fields input,
.outline-review[data-variant="inline"].is-editing .outline-review__node-fields textarea { padding-inline:7px; }
.outline-review[data-variant="inline"] .outline-review__node-actions { align-self:center; padding:0; }
.outline-review[data-variant="inline"] .outline-review__footer { padding:12px 20px; }
@keyframes outline-review-spin { to { transform:rotate(360deg); } }
@media (max-width:767px) {
  .outline-review { padding:0 16px; }
  .outline-review__setup { min-height:0; }
  .outline-review__starting-point { margin:0; padding:11px 0 13px; }
  .outline-review__starting-point > div { grid-template-columns:1fr; gap:8px; }
  .outline-retrieval { padding:14px 0 16px; }
  .outline-retrieval__diff,.outline-retrieval__sources { grid-template-columns:1fr; }
  .outline-retrieval__diff section + section,.outline-retrieval__source + .outline-retrieval__source { padding-left:0; border-left:0; border-top:1px solid #e4e7f5; }
  .outline-review__adjustment {
    grid-template-columns:1fr;
    gap:8px;
    margin:0;
    padding:11px 0;
  }
  .outline-review__adjustment button { width:100%; }
  .outline-review__node-ai-panel { margin:0 0 12px; }
  .outline-review__node-ai-input { grid-template-columns:18px minmax(0,1fr); }
  .outline-review__node-ai-input > button { grid-column:2; justify-self:end; }
  .outline-review__node-proposal { align-items:stretch; flex-direction:column; }
  .outline-review__node-proposal-actions { justify-content:flex-end; }
  .outline-review__proposal-notice { margin:0; padding:6px 0 10px; }
  .outline-review__proposal { width:auto; margin:0 0 11px; }
  .outline-review__proposal summary { align-items:flex-start; flex-direction:column; gap:4px; }
  .outline-review__diff-groups { grid-template-columns:1fr; }
  .outline-review__proposal-actions { display:grid; grid-template-columns:1fr 1.25fr; }
  .outline-review__proposal-actions button { width:100%; }
  .outline-view-switch { padding-inline:0; }
  .outline-review[data-variant="inline"] .outline-view-switch { padding-inline:14px; }
  .outline-review[data-variant="inline"] .formal-outline { padding-inline:14px; }
  .outline-review[data-variant="inline"] .outline-review__chapters { padding:20px 14px 30px; }
  .formal-outline__masthead { padding:30px 24px 24px; }
  .formal-outline__masthead h1 { font-size:28px; }
  .formal-outline__masthead dl { gap:12px 20px; margin-top:22px; }
  .formal-outline__brief { grid-template-columns:1fr; padding:30px 12px; }
  .formal-outline__brief > div { padding:0; }
  .formal-outline__brief > div + div { margin-top:28px; padding:28px 0 0; border-top:1px solid #e7e9ef; border-left:0; }
  .outline-quality,.formal-outline__schedule { margin-inline:12px; padding-inline:0; }
  .outline-quality > header,.formal-outline__schedule > header { align-items:flex-start; flex-direction:column; gap:8px; }
  .outline-quality > header > p,.formal-outline__schedule > header p { text-align:left; }
  .outline-quality li { grid-template-columns:1fr; gap:9px; }
  .outline-quality li button { justify-self:start; }
  .formal-outline__chapter-block > header { grid-template-columns:32px minmax(0,1fr); gap:10px; }
  .formal-outline__chapter-block > header small { grid-column:2; }
  .formal-outline__chapter-block > ol { margin-left:42px; }
  .formal-outline__chapter-block > ol > li { grid-template-columns:1fr; gap:5px; }
  .outline-review__chapters { gap:16px; padding:16px 0 20px; }
  .outline-review__chapter-heading { padding:11px 10px; border-radius:8px; }
  .outline-review__chapter-heading input { font-size:16px; }
  .outline-review__section-list { margin-left:14px; }
  .outline-review__section { padding:11px 2px 11px 10px; }
  .outline-review__chapter-heading,.outline-review__section { grid-template-columns:minmax(0,1fr); }
  .outline-review__node-actions { justify-content:flex-end; padding-top:0; }
  .outline-review__footer { align-items:stretch; flex-direction:column; gap:9px; padding:11px 0 13px; }
  .outline-review__actions { display:grid; grid-template-columns:.85fr 1.15fr; }
  .outline-review__actions button { padding:0 9px; }
}
@media (prefers-reduced-motion:reduce) {
  .outline-review__loading svg,
  .outline-review__actions svg,
  .formal-outline,
  .outline-quality svg { animation:none!important; }
}
</style>
