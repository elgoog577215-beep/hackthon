<template>
  <section
    ref="outlineRoot"
    class="outline-review"
    :class="{ 'is-editing': editable, 'is-ai-candidate': adjustmentProposal }"
    :data-mode="editable ? 'edit' : 'view'"
    :data-variant="variant"
    :aria-label="t('courseGeneration.outlineReview.ariaLabel', '课程大纲')"
  >
    <article class="outline-review__sheet" :class="{ 'has-ai-candidate': surface === 'teacher' && adjustmentProposal }">
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
        <div v-if="surface === 'teacher' && adjustmentProposal" class="outline-candidate-notice" role="status">
          <div>
            <Sparkles :size="16" />
            <span>
              <strong>{{ t('courseWorkbench.aiCollaboration.outlineCandidateTitle', 'AI 候选已嵌入大纲正文') }}</strong>
              <small>{{ t('courseWorkbench.aiCollaboration.inlineCandidateBoundary', '原文仍然保留，只有采用后候选才会写入正式大纲。') }}</small>
            </span>
          </div>
          <nav :aria-label="t('courseWorkbench.aiCollaboration.inlineCandidateActions', 'AI 候选操作')">
            <button type="button" :disabled="adjustmentBusy || requestBusy" @click="openInlineAi">
              <Sparkles :size="14" />{{ t('courseWorkbench.aiCollaboration.iterateCandidate', '继续调整') }}
            </button>
            <button type="button" :disabled="adjustmentBusy || requestBusy" @click="resolveAiCandidate(false)">
              <X :size="14" />{{ t('courseWorkbench.aiCollaboration.keepOriginal', '保留原文') }}
            </button>
            <button class="primary" type="button" :disabled="adjustmentBusy || requestBusy || !adjustmentProposal.can_apply" @click="resolveAiCandidate(true)">
              <LoaderCircle v-if="adjustmentBusy || requestBusy" :size="14" />
              <CircleCheck v-else :size="14" />{{ t('courseWorkbench.aiCollaboration.applyCandidate', '采用修改') }}
            </button>
          </nav>
        </div>

        <TextSelectionAiAction
          v-if="surface === 'teacher'"
          ref="inlineAiAction"
          :container="outlineRoot"
          :disabled="editable"
          :busy="adjustmentBusy || requestBusy"
          :label="t('courseWorkbench.aiCollaboration.selectionModify', 'AI 修改')"
          :composer-title="t('courseWorkbench.aiCollaboration.inlineComposerTitle', '告诉 AI 怎么改')"
          :placeholder="t('courseWorkbench.aiCollaboration.selectionPlaceholder', '说明你想怎样修改选中内容…')"
          :submit-label="t('courseWorkbench.aiCollaboration.inlineGenerate', '生成修改')"
          :cancel-label="t('common.cancel', '取消')"
          :working-label="t('courseWorkbench.aiCollaboration.inlineWorking', '正在生成候选…')"
          :selection-label="t('courseWorkbench.aiCollaboration.inlineSelectionScope', '修改选中内容')"
          :block-label="t('courseWorkbench.aiCollaboration.inlineBlockScope', '修改当前段落')"
          :document-label="t('courseWorkbench.aiCollaboration.inlineOutlineScope', '修改当前大纲')"
          :boundary-label="t('courseWorkbench.aiCollaboration.inlineBoundary', 'AI 只生成候选，采用后才会写入正式内容。')"
          target-selector="h2[data-node-id], h3[data-node-id], [data-node-body], p, li, blockquote"
          @invoke="emit('open-ai-selection', $event)"
        />

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
            <MathText v-if="coverageVerdict.coverage_promise" tag="p" :content="coverageVerdict.coverage_promise" />
            <div
              v-if="coverageUncovered.length"
              class="outline-coverage__uncovered"
              data-testid="outline-coverage-uncovered"
            >
              <span>{{ t('courseGeneration.outlineReview.coverageUncovered', '本次不覆盖') }}</span>
              <ul>
                <li v-for="topic in coverageUncovered" :key="topic"><MathText :content="topic" /></li>
              </ul>
            </div>
            <ul v-if="coverageAdvisories.length" class="outline-coverage__advisories">
              <li v-for="item in coverageAdvisories" :key="item"><MathText :content="item" /></li>
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
            <MathText tag="p" :content="retrievalProposal.reason || t('courseGeneration.outlineReview.retrievalReasonFallback', '外部资料建议调整当前课程结构。')" />
            <div class="outline-retrieval__shape">
              <span>{{ shapeSummary(retrievalProposal.diff?.before) }}</span>
              <ArrowRight :size="13" />
              <span>{{ shapeSummary(retrievalProposal.diff?.after) }}</span>
            </div>
            <div class="outline-retrieval__diff">
              <section v-for="group in retrievalDiffGroups" :key="group.key" v-show="group.items.length">
                <h3><MathText :content="group.label" /></h3>
                <ul>
                  <li v-for="item in group.items" :key="`${group.key}-${item.node_id || item.node_name}`">
                    <MathText :content="item.node_name || item.title" />
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
                <strong><MathText :content="source.title || source.domain" /></strong>
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
                <MathText :content="projectDeliverable || t('courseGeneration.outlineReview.deliverablePending', '按项目目标确定')" />
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.experience', '已有经验') }}</small>
                <MathText :content="startingStrengths || t('courseGeneration.outlineReview.notProvided', '暂未提供')" />
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.focusAreas', '重点补充') }}</small>
                <MathText :content="startingFocus || t('courseGeneration.outlineReview.discoverInProject', '将在项目过程中继续识别')" />
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
                <MathText :content="courseIntent.core_question" />
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.evidenceScope', '证据范围') }}</small>
                <MathText :content="courseIntent.evidence_scope || t('courseGeneration.outlineReview.notProvided', '暂未提供')" />
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.desiredOutput', '结论形态') }}</small>
                <MathText :content="courseIntent.desired_output" />
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
                <MathText :content="courseIntent.exam_name" />
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.examScope', '考纲范围') }}</small>
                <MathText :content="courseIntent.exam_scope" />
              </p>
              <p>
                <small>{{ t('courseGeneration.outlineReview.currentPreparation', '当前准备度') }}</small>
                <MathText :content="courseIntent.current_preparation || t('courseGeneration.outlineReview.notProvided', '暂未提供')" />
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
              <MathText tag="p" class="outline-review__proposal-summary" :content="adjustmentProposal.summary" />

              <div class="outline-review__diff-groups">
                <section v-if="adjustmentProposal.diff?.added?.length">
                  <h3>{{ t('courseGeneration.outlineReview.diffAdded', '新增') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.added" :key="`added-${item.node_id || item.node_name}`">
                      <MathText :content="item.node_name" /><small>{{ item.new_position }}</small>
                    </li>
                  </ul>
                </section>
                <section v-if="adjustmentProposal.diff?.removed?.length">
                  <h3>{{ t('courseGeneration.outlineReview.diffRemoved', '删除') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.removed" :key="`removed-${item.node_id || item.node_name}`">
                      <MathText :content="item.node_name" /><small>{{ item.old_position }}</small>
                    </li>
                  </ul>
                </section>
                <section v-if="adjustmentProposal.diff?.moved?.length">
                  <h3>{{ t('courseGeneration.outlineReview.diffMoved', '移动') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.moved" :key="`moved-${item.node_id || item.node_name}`">
                      <MathText :content="item.node_name" />
                      <small>{{ item.old_position }} → {{ item.new_position }}</small>
                    </li>
                  </ul>
                </section>
                <section v-if="adjustmentProposal.diff?.updated?.length">
                  <h3>{{ t('courseGeneration.outlineReview.diffUpdated', '内容修改') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.updated" :key="`updated-${item.node_id || item.node_name}`">
                      <MathText :content="item.node_name" />
                      <small>{{ changedFieldSummary(item.changes) }}</small>
                    </li>
                  </ul>
                </section>
                <section v-if="adjustmentProposal.diff?.course_updated?.length">
                  <h3>{{ t('courseGeneration.outlineReview.courseLevelChanges', '课程级内容修改') }}</h3>
                  <ul>
                    <li v-for="item in adjustmentProposal.diff.course_updated" :key="`course-${item.field}`">
                      <span>{{ coursePlanFieldLabel(item.field) }}</span>
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

          <div
            v-if="editable && (!isLectureOutline || isLightOutline)"
            class="outline-document-toolbar"
            :class="{ 'is-locked': Boolean(adjustmentProposal) }"
            role="toolbar"
            :aria-label="t('courseGeneration.outlineReview.editorToolbar', '大纲编辑工具栏')"
          >
            <div class="outline-editor-modes" :aria-label="t('courseGeneration.outlineReview.editorMode', '编辑方式')">
              <button
                type="button"
                :class="{ 'is-active': editorMode === 'visual' }"
                :aria-pressed="editorMode === 'visual'"
                @click="setEditorMode('visual')"
              >
                <FileType2 :size="15" />{{ t('courseGeneration.outlineReview.visualMode', '文档') }}
              </button>
              <button
                type="button"
                :class="{ 'is-active': editorMode === 'markdown' }"
                :aria-pressed="editorMode === 'markdown'"
                @click="setEditorMode('markdown')"
              >
                <Braces :size="15" />Markdown
              </button>
            </div>

            <template v-if="editorMode === 'visual'">
              <i aria-hidden="true" />
              <div class="outline-document-toolbar__group outline-document-toolbar__history">
                <button class="format-icon" type="button" :disabled="adjustmentBusy" :title="t('common.undo', '撤销')" @mousedown.prevent="runEditorCommand('undo')">
                  <Undo2 :size="16" /><span>{{ t('common.undo', '撤销') }}</span>
                </button>
                <button class="format-icon" type="button" :disabled="adjustmentBusy" :title="t('common.redo', '重做')" @mousedown.prevent="runEditorCommand('redo')">
                  <Redo2 :size="16" /><span>{{ t('common.redo', '重做') }}</span>
                </button>
              </div>
              <label class="outline-block-style">
                <span>{{ t('courseGeneration.outlineReview.textStyle', '文字样式') }}</span>
                <select :disabled="adjustmentBusy" :aria-label="t('courseGeneration.outlineReview.textStyle', '文字样式')" @change="applyEditorBlockStyle">
                  <option value="p">{{ t('courseGeneration.outlineReview.bodyText', '正文') }}</option>
                  <option value="h2">{{ isLectureOutline ? t('courseGeneration.outlineReview.lectureHeading', '讲次标题') : t('courseGeneration.outlineReview.chapterHeading', '章标题') }}</option>
                  <option v-if="!isLectureOutline" value="h3">{{ t('courseGeneration.outlineReview.sectionHeading', '小节标题') }}</option>
                </select>
              </label>
              <i aria-hidden="true" />
              <div class="outline-document-toolbar__group">
                <button class="format-icon" type="button" :disabled="adjustmentBusy" :title="t('courseGeneration.outlineReview.bold', '加粗')" @mousedown.prevent="runEditorCommand('bold')">
                  <Bold :size="16" /><span>{{ t('courseGeneration.outlineReview.bold', '加粗') }}</span>
                </button>
                <button class="format-icon" type="button" :disabled="adjustmentBusy" :title="t('courseGeneration.outlineReview.italic', '斜体')" @mousedown.prevent="runEditorCommand('italic')">
                  <Italic :size="16" /><span>{{ t('courseGeneration.outlineReview.italic', '斜体') }}</span>
                </button>
                <button class="format-icon" type="button" :disabled="adjustmentBusy" :title="t('courseGeneration.outlineReview.underline', '下划线')" @mousedown.prevent="runEditorCommand('underline')">
                  <Underline :size="16" /><span>{{ t('courseGeneration.outlineReview.underline', '下划线') }}</span>
                </button>
              </div>
              <i aria-hidden="true" />
              <div class="outline-document-toolbar__group">
                <button class="format-icon" type="button" :disabled="adjustmentBusy" :title="t('courseGeneration.outlineReview.bulletList', '项目符号')" @mousedown.prevent="runEditorCommand('insertUnorderedList')">
                  <List :size="16" /><span>{{ t('courseGeneration.outlineReview.bulletList', '项目符号') }}</span>
                </button>
                <button class="format-icon" type="button" :disabled="adjustmentBusy" :title="t('courseGeneration.outlineReview.numberedList', '编号')" @mousedown.prevent="runEditorCommand('insertOrderedList')">
                  <ListOrdered :size="16" /><span>{{ t('courseGeneration.outlineReview.numberedList', '编号') }}</span>
                </button>
              </div>
              <div ref="moreControlRef" class="outline-toolbar-control">
                <button
                  type="button"
                  class="outline-menu-trigger"
                  :class="{ 'is-active': moreMenuOpen }"
                  :disabled="adjustmentBusy"
                  aria-haspopup="menu"
                  :aria-expanded="moreMenuOpen"
                  @mousedown.prevent="toggleMoreMenu"
                >
                  <MoreHorizontal :size="16" />{{ t('courseGeneration.outlineReview.moreFormatting', '更多格式') }}<ChevronDown :size="13" />
                </button>
                <div v-if="moreMenuOpen" class="outline-format-menu" role="menu">
                  <section>
                    <span>{{ t('courseGeneration.outlineReview.alignment', '段落对齐') }}</span>
                    <div>
                      <button type="button" role="menuitem" :title="t('courseGeneration.outlineReview.alignLeft', '左对齐')" @mousedown.prevent="applyEditorAlignment('left')"><AlignLeft :size="17" /></button>
                      <button type="button" role="menuitem" :title="t('courseGeneration.outlineReview.alignCenter', '居中')" @mousedown.prevent="applyEditorAlignment('center')"><AlignCenter :size="17" /></button>
                      <button type="button" role="menuitem" :title="t('courseGeneration.outlineReview.alignRight', '右对齐')" @mousedown.prevent="applyEditorAlignment('right')"><AlignRight :size="17" /></button>
                      <button type="button" role="menuitem" :title="t('courseGeneration.outlineReview.alignJustify', '两端对齐')" @mousedown.prevent="applyEditorAlignment('justify')"><AlignJustify :size="17" /></button>
                    </div>
                  </section>
                  <section>
                    <span>{{ t('courseGeneration.outlineReview.paragraph', '段落') }}</span>
                    <div>
                      <button type="button" role="menuitem" :title="t('courseGeneration.outlineReview.decreaseIndent', '减少缩进')" @mousedown.prevent="adjustEditorIndent(-1)"><IndentDecrease :size="17" /></button>
                      <button type="button" role="menuitem" :title="t('courseGeneration.outlineReview.increaseIndent', '增加缩进')" @mousedown.prevent="adjustEditorIndent(1)"><IndentIncrease :size="17" /></button>
                    </div>
                  </section>
                  <section>
                    <span>{{ t('courseGeneration.outlineReview.character', '字符') }}</span>
                    <div>
                      <button type="button" role="menuitem" :title="t('courseGeneration.outlineReview.strikethrough', '删除线')" @mousedown.prevent="runEditorCommand('strikeThrough')"><Strikethrough :size="17" /></button>
                      <button type="button" role="menuitem" :title="t('courseGeneration.outlineReview.superscript', '上标')" @mousedown.prevent="runEditorCommand('superscript')"><Superscript :size="17" /></button>
                      <button type="button" role="menuitem" :title="t('courseGeneration.outlineReview.subscript', '下标')" @mousedown.prevent="runEditorCommand('subscript')"><Subscript :size="17" /></button>
                      <button type="button" role="menuitem" :title="t('courseGeneration.outlineReview.highlight', '高亮')" @mousedown.prevent="highlightEditorSelection"><Highlighter :size="17" /></button>
                    </div>
                  </section>
                  <button type="button" class="outline-format-menu__clear" role="menuitem" @mousedown.prevent="clearEditorFormatting">
                    <RemoveFormatting :size="16" />{{ t('courseGeneration.outlineReview.clearFormatting', '清除格式') }}
                  </button>
                  <small class="outline-format-menu__count">{{ t('courseGeneration.outlineReview.characterCount', '{count} 字').replace('{count}', String(editorCharacterCount)) }}</small>
                </div>
              </div>
              <div ref="insertControlRef" class="outline-insert-control">
                <button
                  type="button"
                  class="outline-insert-trigger"
                  :class="{ 'is-active': insertMenuOpen }"
                  :disabled="adjustmentBusy"
                  aria-haspopup="menu"
                  :aria-expanded="insertMenuOpen"
                  @mousedown.prevent="toggleInsertMenu"
                >
                  <Plus :size="15" />{{ t('courseGeneration.outlineReview.insert', '插入') }}<ChevronDown :size="13" />
                </button>
                <div v-if="insertMenuOpen" class="outline-insert-menu" role="menu">
                  <button type="button" role="menuitem" @mousedown.prevent="insertEditorTable">
                    <Table2 :size="17" /><span><strong>{{ t('courseGeneration.outlineReview.insertTable', '表格') }}</strong><small>3 × 3</small></span>
                  </button>
                  <button type="button" role="menuitem" @mousedown.prevent="insertEditorDiagram">
                    <ChartNoAxesCombined :size="17" /><span><strong>{{ t('courseGeneration.outlineReview.insertDiagram', '流程图') }}</strong><small>{{ t('courseGeneration.outlineReview.insertDiagramHelp', 'Markdown 中实时预览') }}</small></span>
                  </button>
                  <button type="button" role="menuitem" @mousedown.prevent="openInsertPrompt('formula')">
                    <Sigma :size="17" /><span><strong>{{ t('courseGeneration.outlineReview.insertFormula', '公式') }}</strong><small>{{ t('courseGeneration.outlineReview.insertFormulaHelp', '支持 LaTeX') }}</small></span>
                  </button>
                  <button type="button" role="menuitem" @mousedown.prevent="openInsertPrompt('link')">
                    <Link2 :size="17" /><span><strong>{{ t('courseGeneration.outlineReview.insertLink', '链接') }}</strong><small>{{ t('courseGeneration.outlineReview.insertLinkHelp', '选中文字后添加') }}</small></span>
                  </button>
                  <button type="button" role="menuitem" @mousedown.prevent="openInsertPrompt('image')">
                    <ImagePlus :size="17" /><span><strong>{{ t('courseGeneration.outlineReview.insertImage', '图片') }}</strong><small>{{ t('courseGeneration.outlineReview.insertImageHelp', '通过图片地址插入') }}</small></span>
                  </button>
                  <button type="button" role="menuitem" @mousedown.prevent="insertEditorBlock('blockquote')">
                    <Quote :size="17" /><span><strong>{{ t('courseGeneration.outlineReview.insertQuote', '引用') }}</strong><small>{{ t('courseGeneration.outlineReview.insertQuoteHelp', '重点说明') }}</small></span>
                  </button>
                  <button type="button" role="menuitem" @mousedown.prevent="insertEditorBlock('pre')">
                    <Code2 :size="17" /><span><strong>{{ t('courseGeneration.outlineReview.insertCode', '代码块') }}</strong><small>{{ t('courseGeneration.outlineReview.insertCodeHelp', '程序代码') }}</small></span>
                  </button>
                  <button type="button" role="menuitem" @mousedown.prevent="insertEditorDivider">
                    <Minus :size="17" /><span><strong>{{ t('courseGeneration.outlineReview.insertDivider', '分隔线') }}</strong><small>{{ t('courseGeneration.outlineReview.insertDividerHelp', '划分内容段落') }}</small></span>
                  </button>
                </div>
                <form v-if="insertPrompt" class="outline-insert-prompt" @submit.prevent="confirmInsertPrompt">
                  <label>
                    <span>{{ insertPrompt === 'formula'
                      ? t('courseGeneration.outlineReview.formulaSource', 'LaTeX 公式')
                      : insertPrompt === 'link'
                        ? t('courseGeneration.outlineReview.linkAddress', '链接地址')
                        : t('courseGeneration.outlineReview.imageAddress', '图片地址') }}</span>
                    <input
                      ref="insertUrlInputRef"
                      v-model="insertUrl"
                      :type="insertPrompt === 'formula' ? 'text' : 'url'"
                      :inputmode="insertPrompt === 'formula' ? 'text' : 'url'"
                      required
                      :placeholder="insertPrompt === 'formula' ? 'E = mc^2' : 'https://'"
                    />
                  </label>
                  <div>
                    <button type="button" @click="closeInsertControls">{{ t('common.cancel', '取消') }}</button>
                    <button type="submit" class="primary">{{ t('courseGeneration.outlineReview.insertNow', '插入') }}</button>
                  </div>
                </form>
              </div>
              <div ref="findControlRef" class="outline-toolbar-control outline-find-control">
                <button
                  type="button"
                  class="outline-menu-trigger outline-find-trigger"
                  :class="{ 'is-active': findPanelOpen }"
                  :disabled="adjustmentBusy"
                  :aria-expanded="findPanelOpen"
                  @mousedown.prevent="toggleFindPanel"
                >
                  <Search :size="15" />{{ t('courseGeneration.outlineReview.find', '查找') }}
                </button>
                <form v-if="findPanelOpen" class="outline-find-panel" @submit.prevent="stepFindMatch(1)">
                  <label>
                    <span>{{ t('courseGeneration.outlineReview.findText', '查找内容') }}</span>
                    <div>
                      <Search :size="15" />
                      <input
                        ref="findInputRef"
                        v-model="findQuery"
                        type="search"
                        :placeholder="t('courseGeneration.outlineReview.findPlaceholder', '输入要查找的文字')"
                        @input="refreshFindMatches(true)"
                        @keydown.enter.prevent="stepFindMatch($event.shiftKey ? -1 : 1)"
                        @keydown.esc.prevent="closeFindPanel"
                      />
                      <small>{{ findMatchCount ? `${findMatchIndex + 1}/${findMatchCount}` : '0/0' }}</small>
                    </div>
                  </label>
                  <div class="outline-find-panel__navigation">
                    <button type="button" :disabled="!findMatchCount" :title="t('courseGeneration.outlineReview.previousMatch', '上一个')" @click="stepFindMatch(-1)"><ChevronUp :size="15" /></button>
                    <button type="button" :disabled="!findMatchCount" :title="t('courseGeneration.outlineReview.nextMatch', '下一个')" @click="stepFindMatch(1)"><ChevronDown :size="15" /></button>
                  </div>
                  <label>
                    <span>{{ t('courseGeneration.outlineReview.replaceWith', '替换为') }}</span>
                    <div><Replace :size="15" /><input v-model="replaceQuery" type="text" /></div>
                  </label>
                  <div class="outline-find-panel__actions">
                    <button type="button" :disabled="!findMatchCount" @click="replaceCurrentMatch">{{ t('courseGeneration.outlineReview.replace', '替换') }}</button>
                    <button type="button" :disabled="!findMatchCount" @click="replaceAllMatches">{{ t('courseGeneration.outlineReview.replaceAll', '全部替换') }}</button>
                  </div>
                </form>
              </div>
            </template>
            <p v-else class="outline-markdown-guide">
              <Heading2 :size="14" />## {{ isLectureOutline ? t('courseGeneration.outlineReview.lectureHeading', '讲次标题') : t('courseGeneration.outlineReview.chapterHeading', '章标题') }}
              <template v-if="!isLectureOutline">
                <span>·</span>
                <Heading3 :size="14" />### {{ t('courseGeneration.outlineReview.sectionHeading', '小节标题') }}
              </template>
            </p>
          </div>

          <article
            v-if="blueprintNodes.length"
            ref="chaptersRef"
            class="formal-outline"
            :class="{
              'formal-outline--light': isLightOutline,
              'formal-outline--editing': editable,
            }"
            :data-outline-stage="isLightOutline ? 'light' : 'full'"
            data-testid="formal-outline-document"
          >
            <template v-if="isLightOutline">
              <header class="formal-outline__masthead formal-outline__masthead--light">
                <div class="formal-outline__kicker">
                  <FileText :size="15" />
                  <span>{{ t('courseGeneration.outlineReview.lightDocumentKicker', '讲次方案') }}</span>
                </div>
                <h1><MathText :content="documentTitle" /></h1>
                <p>{{ t('courseGeneration.outlineReview.lightDocumentHint', '本轮只确定每讲讲什么。可调整讲次标题与内容简介，再生成完整大纲。') }}</p>
                <dl>
                  <div><dt>{{ t('courseGeneration.outlineReview.documentLectures', '讲次') }}</dt><dd>{{ documentChapters.length }}</dd></div>
                </dl>
              </header>
            </template>

            <template v-else>
              <header class="formal-outline__masthead">
              <div class="formal-outline__kicker">
                <FileText :size="15" />
                <span>{{ t('courseGeneration.outlineReview.documentKicker', '正式教学大纲') }}</span>
              </div>
              <h1><MathText :content="documentTitle" /></h1>
              <MathText tag="p" :content="documentPositioning || t('courseGeneration.outlineReview.lecturePositioningPending', '课程定位将在教学目标与讲次安排中继续明确。')" />
              <dl>
                <div><dt>{{ isLectureOutline ? t('courseGeneration.outlineReview.documentLectures', '讲次') : t('courseGeneration.outlineReview.documentChapters', '章节') }}</dt><dd>{{ documentChapters.length }}</dd></div>
                <div v-if="!isLectureOutline && documentVisibleSectionCount"><dt>{{ t('courseGeneration.outlineReview.documentSections', '小节') }}</dt><dd>{{ documentVisibleSectionCount }}</dd></div>
              </dl>
            </header>

            <section v-if="!isLectureOutline" class="formal-outline__brief">
              <div>
                <h2>{{ t('courseGeneration.outlineReview.courseOutcomes', '课程学习成果') }}</h2>
                <ol v-if="documentObjectives.length">
                  <li v-for="(objective, index) in documentObjectives" :key="`${index}-${objective}`"><MathText :content="objective" /></li>
                </ol>
                <p v-else>{{ t('courseGeneration.outlineReview.outcomesPending', '暂未形成独立的全课成果条目。') }}</p>
              </div>
              <div>
                <h2>{{ t('courseGeneration.outlineReview.prerequisites', '先修要求') }}</h2>
                <ul v-if="documentPrerequisites.length">
                  <li v-for="(item, index) in documentPrerequisites" :key="`${index}-${item}`"><MathText :content="item" /></li>
                </ul>
                <p v-else>{{ t('courseGeneration.outlineReview.noPrerequisites', '无明确先修要求；按课程内学习路径逐步建立基础。') }}</p>
              </div>
            </section>

            <template v-if="isLectureOutline">
              <section class="formal-outline__template-section">
                <h2>{{ t('courseGeneration.outlineReview.templateCourseIntro', '一、课程介绍') }}</h2>
                <h3>{{ t('courseGeneration.outlineReview.templateChineseIntro', '中文简介') }}</h3>
                <MathText tag="p" :content="documentIntroZh || t('courseGeneration.outlineReview.introPending', '尚未确认中文课程简介。')" />
                <h3>{{ t('courseGeneration.outlineReview.templateEnglishIntro', '英文简介') }}</h3>
                <MathText tag="p" :content="documentIntroEn || t('courseGeneration.outlineReview.englishIntroPending', '尚未确认英文课程简介。')" />
              </section>

              <section class="formal-outline__template-section">
                <h2>{{ t('courseGeneration.outlineReview.templateObjectives', '二、教学目标') }}</h2>
                <template v-for="group in formalObjectiveGroups" :key="group.label">
                  <h3>{{ group.label }}</h3>
                  <ul v-if="group.items.length"><li v-for="item in group.items" :key="item"><MathText :content="item" /></li></ul>
                  <p v-else>{{ t('courseGeneration.outlineReview.templatePending', '尚未确认。') }}</p>
                </template>
                <h3>{{ t('courseGeneration.outlineReview.outcomeAlignmentTitle', '课程目标与预期成果关联表') }}</h3>
                <div class="formal-outline__table-wrap">
                  <table data-testid="outcome-alignment-table">
                    <thead>
                      <tr>
                        <th>{{ t('courseGeneration.outlineReview.outcomeAlignmentOutcome', '可测量成果') }}</th>
                        <th>{{ t('courseGeneration.outlineReview.outcomeAlignmentObjectives', '对应目标') }}</th>
                        <th>{{ t('courseGeneration.outlineReview.outcomeAlignmentLectures', '覆盖讲次') }}</th>
                        <th>{{ t('courseGeneration.outlineReview.outcomeAlignmentEvidence', '评价证据') }}</th>
                        <th>{{ t('courseGeneration.outlineReview.outcomeAlignmentScope', '内容覆盖范围') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-if="!documentOutcomeAlignment.length">
                        <td colspan="5">{{ t('courseGeneration.outlineReview.outcomeAlignmentPending', '尚未建立目标与成果关联。') }}</td>
                      </tr>
                      <tr v-for="item in documentOutcomeAlignment" :key="`${item.outcomeNumber}-${item.outcome}`">
                        <td><MathText :content="item.outcome" /></td>
                        <td><MathText :content="item.objectiveRefs.join('、') || '—'" /></td>
                        <td><MathText :content="item.lectureLabels.join('、') || '—'" /></td>
                        <td><MathText :content="item.assessmentEvidence.join('；') || '—'" /></td>
                        <td><MathText :content="item.coverageScope || '—'" /></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>

              <section class="formal-outline__template-section">
                <h2>{{ t('courseGeneration.outlineReview.templateRequirements', '三、课程要求') }}</h2>
                <h3>{{ t('courseGeneration.outlineReview.templateTeachingMethods', '授课方式') }}</h3>
                <ul v-if="documentTeachingMethods.length"><li v-for="item in documentTeachingMethods" :key="item"><MathText :content="item" /></li></ul>
                <p v-else>{{ t('courseGeneration.outlineReview.templatePending', '尚未确认。') }}</p>
                <h3>{{ t('courseGeneration.outlineReview.hourAllocationTitle', '学时分配') }}</h3>
                <div class="formal-outline__table-wrap">
                  <table data-testid="outline-hour-allocation">
                    <thead><tr><th>{{ t('courseGeneration.outlineReview.hourType', '教学环节') }}</th><th>{{ t('courseGeneration.outlineReview.calendarHours', '学时') }}</th><th>{{ t('courseGeneration.outlineReview.hourCounting', '是否计入总学时') }}</th></tr></thead>
                    <tbody>
                      <tr v-for="item in documentHourAllocation" :key="item.key"><td>{{ item.label }}</td><td>{{ item.hours }}</td><td>{{ item.counted ? t('common.yes', '是') : t('common.no', '否') }}</td></tr>
                    </tbody>
                  </table>
                </div>
                <h3>{{ t('courseGeneration.outlineReview.templateAssessmentMethods', '考核方式') }}</h3>
                <div v-if="documentAssessmentPlan.length" class="formal-outline__table-wrap">
                  <table data-testid="outline-assessment-plan">
                    <thead><tr><th>{{ t('courseGeneration.outlineReview.assessmentItem', '考核项目') }}</th><th>{{ t('courseGeneration.outlineReview.assessmentCategory', '性质') }}</th><th>{{ t('courseGeneration.outlineReview.assessmentWeight', '权重') }}</th><th>{{ t('courseGeneration.outlineReview.assessmentCriteria', '评分标准') }}</th><th>{{ t('courseGeneration.outlineReview.assessmentOutcomes', '对应成果') }}</th></tr></thead>
                    <tbody><tr v-for="(item, index) in documentAssessmentPlan" :key="`${index}-${item.item}`"><td><MathText :content="item.item" /></td><td>{{ item.categoryLabel }}</td><td>{{ item.weight }}%</td><td><MathText :content="item.criteria || '—'" /></td><td><MathText :content="item.outcomes.join('、') || '—'" /></td></tr></tbody>
                  </table>
                </div>
                <template v-else>
                  <ul v-if="documentAssessmentMethods.length"><li v-for="item in documentAssessmentMethods" :key="item"><MathText :content="item" /></li></ul>
                  <p v-else>{{ t('courseGeneration.outlineReview.templatePending', '尚未确认。') }}</p>
                </template>
              </section>

              <header class="formal-outline__template-heading">
                <h2>{{ t('courseGeneration.outlineReview.templateSchedule', '四、教学内容及教学安排') }}</h2>
              </header>
              <section class="formal-outline__template-section formal-outline__module-summary">
                <h3>{{ t('courseGeneration.outlineReview.moduleGroupingTitle', '知识模块与讲次范围') }}</h3>
                <div class="formal-outline__table-wrap">
                  <table data-testid="outline-course-modules">
                    <thead><tr><th>{{ t('courseGeneration.outlineReview.moduleName', '知识模块') }}</th><th>{{ t('courseGeneration.outlineReview.outcomeAlignmentLectures', '覆盖讲次') }}</th><th>{{ t('courseGeneration.outlineReview.calendarHours', '学时') }}</th></tr></thead>
                    <tbody>
                      <tr v-if="!documentCourseModules.length"><td colspan="3">{{ t('courseGeneration.outlineReview.moduleGroupingPending', '尚未完成讲次分组。') }}</td></tr>
                      <tr v-for="item in documentCourseModules" :key="item.id"><td><MathText :content="item.title" /></td><td><MathText :content="item.lectures.join('、')" /></td><td>{{ item.hours || '—' }}</td></tr>
                    </tbody>
                  </table>
                </div>
              </section>

              <section
                v-if="editable"
                ref="formalContractEditorRef"
                class="formal-contract-editor"
                data-testid="formal-syllabus-contract-editor"
              >
                <header class="formal-contract-editor__heading">
                  <span>
                    <strong>{{ t('courseGeneration.outlineReview.contractEditorTitle', '编辑完整课程大纲') }}</strong>
                    <small>{{ t('courseGeneration.outlineReview.contractEditorHint', '以下内容就是正式大纲，保存后系统会重新审读学时、考核、模块和每讲内容。') }}</small>
                  </span>
                </header>

                <div class="formal-contract-editor__body">
                  <section>
                    <h3>{{ t('courseGeneration.outlineReview.contractCourseFields', '课程级内容') }}</h3>
                    <div class="formal-contract-editor__grid">
                      <label class="wide" data-outline-field="course_title"><span>{{ t('courseGeneration.outlineReview.courseTitle', '课程标题') }}</span><input :value="documentPlan.course_title || documentTitle" @input="setPlanScalar('course_title', $event)" /></label>
                      <label data-outline-field="course_intro_zh"><span>{{ t('courseGeneration.outlineReview.templateChineseIntro', '中文简介') }}</span><textarea :value="documentPlan.course_intro_zh || ''" rows="4" @input="setPlanScalar('course_intro_zh', $event)" /></label>
                      <label data-outline-field="course_intro_en"><span>{{ t('courseGeneration.outlineReview.templateEnglishIntro', '英文简介') }}</span><textarea :value="documentPlan.course_intro_en || ''" rows="4" @input="setPlanScalar('course_intro_en', $event)" /></label>
                      <label class="wide" data-outline-field="positioning"><span>{{ t('courseGeneration.outlineReview.positioning', '课程定位') }}</span><textarea :value="documentPlan.positioning || ''" rows="3" @input="setPlanScalar('positioning', $event)" /></label>
                      <label data-outline-field="learning_objectives"><span>{{ t('courseGeneration.outlineReview.templateLearningGoals', '学习目标') }}</span><textarea :value="planListText('learning_objectives')" rows="5" @input="setPlanList('learning_objectives', $event)" /></label>
                      <label data-outline-field="prerequisites"><span>{{ t('courseGeneration.outlineReview.prerequisites', '先修要求') }}</span><textarea :value="planListText('prerequisites')" rows="5" @input="setPlanList('prerequisites', $event)" /></label>
                      <label data-outline-field="education_objectives"><span>{{ t('courseGeneration.outlineReview.templateEducationGoals', '育人目标') }}</span><textarea :value="planListText('education_objectives')" rows="5" @input="setPlanList('education_objectives', $event)" /></label>
                      <label data-outline-field="measurable_outcomes"><span>{{ t('courseGeneration.outlineReview.templateMeasurableResults', '可测量结果') }}</span><textarea :value="planListText('measurable_outcomes')" rows="5" @input="setPlanList('measurable_outcomes', $event)" /></label>
                      <label data-outline-field="teaching_methods"><span>{{ t('courseGeneration.outlineReview.templateTeachingMethods', '授课方式') }}</span><textarea :value="planListText('teaching_methods')" rows="5" @input="setPlanList('teaching_methods', $event)" /></label>
                      <label data-outline-field="assessment_methods"><span>{{ t('courseGeneration.outlineReview.templateAssessmentMethods', '考核方式') }}</span><textarea :value="planListText('assessment_methods')" rows="5" @input="setPlanList('assessment_methods', $event)" /></label>
                      <label data-outline-field="reference_books"><span>{{ t('courseGeneration.outlineReview.referenceBooks', '已确认参考书籍') }}</span><textarea :value="planListText('reference_books')" rows="5" @input="setPlanList('reference_books', $event)" /></label>
                      <label data-outline-field="reference_websites"><span>{{ t('courseGeneration.outlineReview.referenceWebsites', '已确认网络资源') }}</span><textarea :value="planListText('reference_websites')" rows="5" @input="setPlanList('reference_websites', $event)" /></label>
                      <label class="wide" data-outline-field="ideology_cases"><span>{{ t('courseGeneration.outlineReview.templateIdeologyAttachment', '思政融合案例') }}</span><textarea :value="ideologyCasesText()" rows="4" @input="setIdeologyCases($event)" /></label>
                      <label class="wide" data-outline-field="course_website"><span>{{ t('courseGeneration.outlineReview.templateCourseWebsite', '课程教学网站') }}</span><input :value="documentPlan.course_website || ''" @input="setPlanScalar('course_website', $event)" /></label>
                    </div>
                  </section>

                  <section>
                    <h3>{{ t('courseGeneration.outlineReview.outcomeAlignmentTitle', '课程目标与预期成果关联表') }}</h3>
                    <div class="formal-contract-editor__rows" data-outline-field="outcome_alignment">
                      <div v-for="(outcome, index) in documentMeasurableOutcomes" :key="`alignment-${index}`" class="formal-contract-editor__row formal-contract-editor__row--alignment">
                        <strong>{{ index + 1 }}. <MathText :content="outcome" /></strong>
                        <input :value="outcomeAlignmentText(index, 'objective_refs')" :placeholder="t('courseGeneration.outlineReview.alignmentObjectivesPlaceholder', '对应目标，换行分隔')" @input="setOutcomeAlignment(index, 'objective_refs', $event)" />
                        <input :value="outcomeAlignmentText(index, 'lecture_numbers')" :placeholder="t('courseGeneration.outlineReview.alignmentLecturesPlaceholder', '讲次，如 1,2,3')" @input="setOutcomeAlignment(index, 'lecture_numbers', $event)" />
                        <input :value="outcomeAlignmentText(index, 'assessment_evidence')" :placeholder="t('courseGeneration.outlineReview.alignmentEvidencePlaceholder', '评价证据，换行分隔')" @input="setOutcomeAlignment(index, 'assessment_evidence', $event)" />
                        <input :value="outcomeAlignmentText(index, 'coverage_scope')" :placeholder="t('courseGeneration.outlineReview.alignmentScopePlaceholder', '内容覆盖范围')" @input="setOutcomeAlignment(index, 'coverage_scope', $event)" />
                      </div>
                    </div>
                  </section>

                  <section>
                    <div class="formal-contract-editor__section-heading">
                      <h3>{{ t('courseGeneration.outlineReview.templateAssessmentMethods', '考核方式') }}</h3>
                      <div><button type="button" @click="addAssessmentRow('formative')">+ {{ t('courseGeneration.outlineReview.assessmentFormative', '过程性评价') }}</button><button type="button" @click="addAssessmentRow('summative')">+ {{ t('courseGeneration.outlineReview.assessmentSummative', '终结性评价') }}</button></div>
                    </div>
                    <div class="formal-contract-editor__rows" data-outline-field="assessment_plan">
                      <div v-for="(item, index) in assessmentPlanRows" :key="`assessment-${index}`" class="formal-contract-editor__row formal-contract-editor__row--assessment">
                        <input :value="item.item || ''" :placeholder="t('courseGeneration.outlineReview.assessmentItem', '考核项目')" @input="setAssessmentField(index, 'item', $event)" />
                        <select :value="item.category || 'formative'" @change="setAssessmentField(index, 'category', $event)"><option value="formative">{{ t('courseGeneration.outlineReview.assessmentFormative', '过程性评价') }}</option><option value="summative">{{ t('courseGeneration.outlineReview.assessmentSummative', '终结性评价') }}</option></select>
                        <input :value="item.weight_percent ?? ''" type="number" min="0" max="100" step="1" :placeholder="t('courseGeneration.outlineReview.assessmentWeight', '权重')" @input="setAssessmentField(index, 'weight_percent', $event)" />
                        <input :value="item.criteria || ''" :placeholder="t('courseGeneration.outlineReview.assessmentCriteria', '评分标准')" @input="setAssessmentField(index, 'criteria', $event)" />
                        <input :value="numberListText(item.outcome_numbers)" :placeholder="t('courseGeneration.outlineReview.assessmentOutcomesPlaceholder', '成果序号，如 1,2')" @input="setAssessmentField(index, 'outcome_numbers', $event)" />
                        <button type="button" :aria-label="t('common.delete', '删除')" @click="removeAssessmentRow(index)">×</button>
                      </div>
                    </div>
                  </section>

                  <section>
                    <div class="formal-contract-editor__section-heading">
                      <h3>{{ t('courseGeneration.outlineReview.moduleGroupingTitle', '知识模块与讲次范围') }}</h3>
                      <button type="button" @click="addModuleRow">+ {{ t('courseGeneration.outlineReview.addModule', '新增模块') }}</button>
                    </div>
                    <div class="formal-contract-editor__rows" data-outline-field="course_modules">
                      <div v-for="(item, index) in courseModuleRows" :key="`module-${index}`" class="formal-contract-editor__row formal-contract-editor__row--module">
                        <input :value="item.title || ''" :placeholder="t('courseGeneration.outlineReview.moduleName', '知识模块')" @input="setModuleField(index, 'title', $event)" />
                        <input :value="numberListText(item.lecture_numbers)" :placeholder="t('courseGeneration.outlineReview.moduleLecturesPlaceholder', '讲次，如 1,2,3')" @input="setModuleField(index, 'lecture_numbers', $event)" />
                        <button type="button" :aria-label="t('common.delete', '删除')" @click="removeModuleRow(index)">×</button>
                      </div>
                    </div>
                  </section>

                  <section>
                    <h3>{{ t('courseGeneration.outlineReview.contractLectureFields', '每讲必备内容') }}</h3>
                    <details v-for="(chapter, lectureIndex) in documentChapters" :key="`contract-${chapter.node_id || lectureIndex}`" class="formal-contract-editor__lecture" :data-outline-node-id="chapter.sections?.[0]?.node_id || chapter.node_id || ''" :open="lectureIndex === 0">
                      <summary><strong>{{ t('courseGeneration.outlineReview.lectureNumber', '第{number}讲').replace('{number}', String(lectureIndex + 1)) }} · <MathText :content="plainLectureTitle(chapter.title)" /></strong></summary>
                      <div>
                        <label class="wide" data-outline-field="node_name"><span>{{ t('courseGeneration.outlineReview.lectureHeading', '讲次标题') }}</span><input :value="plainLectureTitle(chapter.title)" @input="setLectureTitle(lectureIndex, $event)" /></label>
                        <label class="wide" data-outline-field="content_summary"><span>{{ t('courseGeneration.outlineReview.lectureSummaryLabel', '内容简介') }}</span><textarea :value="lectureScalar(lectureIndex, 'content_summary')" rows="4" @input="setLectureScalar(lectureIndex, 'content_summary', $event)" /></label>
                        <label class="wide" data-outline-field="learning_objective"><span>{{ t('courseGeneration.outlineReview.lectureObjectiveLabel', '学习目标') }}</span><textarea :value="lectureScalar(lectureIndex, 'learning_objective')" rows="3" @input="setLectureScalar(lectureIndex, 'learning_objective', $event)" /></label>
                        <label class="wide" data-outline-field="scope_boundary"><span>{{ t('courseGeneration.outlineReview.lectureScopeLabel', '本讲范围') }}</span><textarea :value="lectureScalar(lectureIndex, 'scope_boundary')" rows="3" @input="setLectureScalar(lectureIndex, 'scope_boundary', $event)" /></label>
                        <label data-outline-field="key_points"><span>{{ t('courseGeneration.outlineReview.keyPoints', '教学重点') }}</span><textarea :value="lectureListText(lectureIndex, 'key_points')" rows="4" @input="setLectureList(lectureIndex, 'key_points', $event)" /></label>
                        <label data-outline-field="key_difficulties"><span>{{ t('courseGeneration.outlineReview.keyDifficulties', '教学难点') }}</span><textarea :value="lectureListText(lectureIndex, 'key_difficulties')" rows="4" @input="setLectureList(lectureIndex, 'key_difficulties', $event)" /></label>
                        <label class="wide" data-outline-field="assessment"><span>{{ t('courseGeneration.outlineReview.lectureAssessmentLabel', '达成检验') }}</span><textarea :value="lectureListText(lectureIndex, 'assessment')" rows="4" @input="setLectureList(lectureIndex, 'assessment', $event)" /></label>
                        <label data-outline-field="activities"><span>{{ t('courseGeneration.outlineReview.learningActivities', '教学活动') }}</span><textarea :value="lectureListText(lectureIndex, 'activities')" rows="5" @input="setLectureList(lectureIndex, 'activities', $event)" /></label>
                        <label data-outline-field="homework"><span>{{ t('courseGeneration.outlineReview.homework', '课后作业') }}</span><textarea :value="lectureListText(lectureIndex, 'homework')" rows="5" @input="setLectureList(lectureIndex, 'homework', $event)" /></label>
                        <label class="wide" data-outline-field="application_anchors"><span>{{ t('courseGeneration.outlineReview.applicationAnchorLabel', '应用载体') }}</span><textarea :value="lectureListText(lectureIndex, 'application_anchors')" rows="3" @input="setLectureList(lectureIndex, 'application_anchors', $event)" /></label>
                        <label class="wide"><span>{{ t('courseGeneration.outlineReview.learningTaskLabel', '学习任务') }}</span></label>
                        <div class="formal-contract-editor__rows wide" data-outline-field="learning_tasks">
                          <div v-for="(task, taskIndex) in lectureTasks(lectureIndex)" :key="`task-${taskIndex}`" class="formal-contract-editor__row formal-contract-editor__row--task">
                            <select :value="task.mode || 'offline'" @change="setLectureTaskField(lectureIndex, taskIndex, 'mode', $event)"><option value="offline">{{ t('courseGeneration.outlineReview.taskOffline', '线下') }}</option><option value="online">{{ t('courseGeneration.outlineReview.taskOnline', '线上') }}</option></select>
                            <select :value="task.stage || 'after_class'" @change="setLectureTaskField(lectureIndex, taskIndex, 'stage', $event)"><option value="before_class">{{ t('courseGeneration.outlineReview.beforeClass', '课前') }}</option><option value="after_class">{{ t('courseGeneration.outlineReview.afterClass', '课后') }}</option></select>
                            <input :value="task.task || ''" :placeholder="t('courseGeneration.outlineReview.learningTaskLabel', '学习任务')" @input="setLectureTaskField(lectureIndex, taskIndex, 'task', $event)" />
                            <input :value="task.evidence || ''" :placeholder="t('courseGeneration.outlineReview.taskEvidence', '可提交证据')" @input="setLectureTaskField(lectureIndex, taskIndex, 'evidence', $event)" />
                            <input :value="task.estimated_hours ?? ''" type="number" min="0" max="24" step="0.5" :placeholder="t('courseGeneration.outlineReview.estimatedHours', '课外学时')" @input="setLectureTaskField(lectureIndex, taskIndex, 'estimated_hours', $event)" />
                            <button type="button" :aria-label="t('common.delete', '删除')" @click="removeLectureTask(lectureIndex, taskIndex)">×</button>
                          </div>
                          <button type="button" class="formal-contract-editor__add" @click="addLectureTask(lectureIndex)">+ {{ t('courseGeneration.outlineReview.addLearningTask', '新增学习任务') }}</button>
                        </div>
                        <label class="wide"><span>{{ t('courseGeneration.outlineReview.extensionResourceLabel', '拓展资源') }}</span></label>
                        <div class="formal-contract-editor__rows wide" data-outline-field="extension_resources">
                          <div v-for="(resource, resourceIndex) in lectureResources(lectureIndex)" :key="`resource-${resourceIndex}`" class="formal-contract-editor__row formal-contract-editor__row--resource">
                            <select :value="resource.source_ref || ''" @change="selectLectureResource(lectureIndex, resourceIndex, $event)"><option value="">{{ t('courseGeneration.outlineReview.selectVerifiedReference', '选择已核实来源') }}</option><option v-for="option in confirmedReferenceOptions" :key="option.label" :value="option.label">{{ option.label }}</option></select>
                            <input :value="resource.edition || ''" :placeholder="t('courseGeneration.outlineReview.resourceEdition', '版次（书籍必填）')" @input="setLectureResourceField(lectureIndex, resourceIndex, 'edition', $event)" />
                            <input :value="resource.locator || ''" :placeholder="t('courseGeneration.outlineReview.resourceLocator', '章节或页码')" @input="setLectureResourceField(lectureIndex, resourceIndex, 'locator', $event)" />
                            <button type="button" :aria-label="t('common.delete', '删除')" @click="removeLectureResource(lectureIndex, resourceIndex)">×</button>
                          </div>
                          <button type="button" class="formal-contract-editor__add" :disabled="!confirmedReferenceOptions.length" @click="addLectureResource(lectureIndex)">+ {{ t('courseGeneration.outlineReview.addExtensionResource', '新增拓展资源') }}</button>
                        </div>
                        <fieldset class="formal-contract-editor__hours wide" data-outline-field="hour_breakdown">
                          <legend>{{ t('courseGeneration.outlineReview.hourBreakdownLabel', '讲授 / 实践 / 在线') }}</legend>
                          <label><span>{{ t('courseGeneration.outlineReview.hourClassroomLecture', '线下讲授') }}</span><input :value="lectureHour(lectureIndex, 'classroom_lecture')" type="number" min="0" max="24" step="0.5" @input="setLectureHour(lectureIndex, 'classroom_lecture', $event)" /></label>
                          <label><span>{{ t('courseGeneration.outlineReview.hourClassroomPractice', '线下实践') }}</span><input :value="lectureHour(lectureIndex, 'classroom_practice')" type="number" min="0" max="24" step="0.5" @input="setLectureHour(lectureIndex, 'classroom_practice', $event)" /></label>
                          <label><span>{{ t('courseGeneration.outlineReview.hourOnlineInstruction', '在线教学') }}</span><input :value="lectureHour(lectureIndex, 'online_instruction')" type="number" min="0" max="24" step="0.5" @input="setLectureHour(lectureIndex, 'online_instruction', $event)" /></label>
                        </fieldset>
                        <label class="wide"><span>{{ t('courseGeneration.outlineReview.ideologyGoal', '育人目标') }}</span><textarea :value="lectureListText(lectureIndex, 'education_objective_refs')" rows="2" @input="setLectureList(lectureIndex, 'education_objective_refs', $event)" /></label>
                        <label class="wide"><span>{{ t('courseGeneration.outlineReview.ideologyImplementation', '育人实施方式（有真实联系时填写）') }}</span><textarea :value="lectureScalar(lectureIndex, 'ideology_implementation')" rows="2" @input="setLectureScalar(lectureIndex, 'ideology_implementation', $event)" /></label>
                        <div class="formal-contract-editor__mentor wide">
                          <label><span>{{ t('courseGeneration.outlineReview.externalMentor', '校外导师') }}</span><input :value="lectureMentor(lectureIndex, 'name')" @input="setLectureMentor(lectureIndex, 'name', $event)" /></label>
                          <label><span>{{ t('courseGeneration.outlineReview.mentorOrganization', '单位') }}</span><input :value="lectureMentor(lectureIndex, 'organization')" @input="setLectureMentor(lectureIndex, 'organization', $event)" /></label>
                          <label><span>{{ t('courseGeneration.outlineReview.mentorRole', '参与角色') }}</span><input :value="lectureMentor(lectureIndex, 'role')" @input="setLectureMentor(lectureIndex, 'role', $event)" /></label>
                        </div>
                      </div>
                    </details>
                  </section>
                </div>
              </section>
              </template>
            </template>

            <section
              v-if="editorMode === 'visual' && (!editable || !isLectureOutline || isLightOutline)"
              ref="richEditorRef"
              class="formal-outline__schedule outline-rich-editor"
              :class="{ 'is-editable': editable }"
              :contenteditable="editable && !adjustmentBusy && !adjustmentProposal ? 'true' : 'false'"
              :aria-label="t('courseGeneration.outlineReview.richEditorLabel', '课程大纲正文编辑器')"
              :aria-readonly="!editable"
              :spellcheck="editable"
              data-testid="outline-rich-editor"
              v-html="outlineEditorHtml"
              @input="handleRichEditorInput"
              @change="handleLessonTypeControlChange"
              @blur="syncRichEditorToNodes"
              @paste="handleRichEditorPaste"
              @keydown="handleEditorKeydown"
            />
            <section v-else-if="!isLectureOutline || isLightOutline" class="outline-markdown-workspace" data-testid="outline-markdown-editor">
              <label class="outline-markdown-pane outline-markdown-pane--source">
                <span>{{ t('courseGeneration.outlineReview.markdownSource', 'Markdown 源码') }}</span>
                <textarea
                  v-model="markdownDraft"
                  :disabled="adjustmentBusy"
                  :aria-label="t('courseGeneration.outlineReview.markdownSource', 'Markdown 源码')"
                  spellcheck="false"
                  @input="handleMarkdownInput"
                />
              </label>
              <div class="outline-markdown-pane outline-markdown-pane--preview">
                <span>{{ t('courseGeneration.outlineReview.markdownPreview', '实时预览') }}</span>
                <MarkdownRenderer class="outline-markdown-preview" :content="markdownDraft" :enable-code-run="false" />
              </div>
            </section>

            <section
              v-if="isLectureOutline && !isLightOutline"
              class="formal-outline__lecture-evidence"
              data-testid="lecture-outcome-review"
            >
              <h3>{{ t('courseGeneration.outlineReview.lectureEvidenceTitle', '每讲学习成果与达成标准') }}</h3>
              <ol>
                <li v-for="(chapter, index) in documentChapters" :key="String(chapter.node_id || index)">
                  <header>
                    <span>{{ t('courseGeneration.outlineReview.lectureNumber', '第{number}讲').replace('{number}', String(index + 1)) }}</span>
                    <strong><MathText :content="plainLectureTitle(chapter.title)" /></strong>
                  </header>
                  <dl>
                    <div>
                      <dt>{{ t('courseGeneration.outlineReview.lectureObjectiveLabel', '学习目标') }}</dt>
                      <dd><MathText :content="lectureEvidence(chapter).objective || t('courseGeneration.outlineReview.lectureEvidencePending', '尚未明确，建议补充后再确认。')" /></dd>
                    </div>
                    <div>
                      <dt>{{ t('courseGeneration.outlineReview.lectureScopeLabel', '本讲范围') }}</dt>
                      <dd><MathText :content="lectureEvidence(chapter).scope || t('courseGeneration.outlineReview.lectureEvidencePending', '尚未明确，建议补充后再确认。')" /></dd>
                    </div>
                    <div>
                      <dt>{{ t('courseGeneration.outlineReview.lectureAssessmentLabel', '达成检验') }}</dt>
                      <dd><MathText :content="lectureEvidence(chapter).assessments.join('；') || t('courseGeneration.outlineReview.lectureEvidencePending', '尚未明确，建议补充后再确认。')" /></dd>
                    </div>
                    <div>
                      <dt>{{ t('courseGeneration.outlineReview.applicationAnchorLabel', '应用载体') }}</dt>
                      <dd><MathText :content="lectureContract(chapter).anchors.join('；') || t('courseGeneration.outlineReview.lectureEvidencePending', '尚未明确，建议补充后再确认。')" /></dd>
                    </div>
                    <div>
                      <dt>{{ t('courseGeneration.outlineReview.extensionResourceLabel', '拓展资源') }}</dt>
                      <dd><MathText :content="lectureContract(chapter).resources.join('；') || t('courseGeneration.outlineReview.lectureEvidencePending', '尚未明确，建议补充后再确认。')" /></dd>
                    </div>
                    <div>
                      <dt>{{ t('courseGeneration.outlineReview.learningTaskLabel', '学习任务') }}</dt>
                      <dd><MathText :content="lectureContract(chapter).tasks.join('；') || t('courseGeneration.outlineReview.lectureEvidencePending', '尚未明确，建议补充后再确认。')" /></dd>
                    </div>
                    <div>
                      <dt>{{ t('courseGeneration.outlineReview.hourBreakdownLabel', '讲授 / 实践 / 在线') }}</dt>
                      <dd>{{ lectureContract(chapter).hours }}</dd>
                    </div>
                  </dl>
                </li>
              </ol>
            </section>

            <template v-if="isLectureOutline && !isLightOutline">
              <section class="formal-outline__template-section formal-outline__attachments">
                <div class="formal-outline__attachment-heading">
                  <h3>{{ t('courseGeneration.outlineReview.templateCalendarAttachment', '附件1：课程教学日历') }}</h3>
                  <MathText v-if="documentCalendarBasis" tag="small" :content="documentCalendarBasis" />
                </div>
                <div class="formal-outline__table-wrap">
                  <table>
                    <thead><tr><th>{{ t('courseGeneration.outlineReview.calendarWeek', '周次') }}</th><th>{{ t('courseGeneration.outlineReview.calendarLecture', '讲次') }}</th><th>{{ t('courseGeneration.outlineReview.calendarTopic', '教学主题') }}</th><th>{{ t('courseGeneration.outlineReview.ideologyGoal', '育人目标') }}</th><th>{{ t('courseGeneration.outlineReview.teachingForm', '教学形式') }}</th><th>{{ t('courseGeneration.outlineReview.externalMentor', '校外导师') }}</th><th>{{ t('courseGeneration.outlineReview.calendarHours', '学时') }}</th></tr></thead>
                    <tbody><tr v-for="item in documentLectureSchedule" :key="item.number"><td>{{ item.week }}</td><td>{{ item.number }}</td><td><MathText :content="item.title" /></td><td><MathText :content="item.education || '—'" /></td><td><MathText :content="item.teachingForm" /></td><td><MathText :content="item.mentor || '—'" /></td><td>{{ item.hours }}</td></tr></tbody>
                  </table>
                </div>
                <h3>{{ t('courseGeneration.outlineReview.templateIdeologyAttachment', '附件2：思政融合案例') }}</h3>
                <div class="formal-outline__table-wrap">
                  <table>
                    <thead><tr><th>{{ t('courseGeneration.outlineReview.calendarLecture', '讲次') }}</th><th>{{ t('courseGeneration.outlineReview.ideologyContent', '课程内容') }}</th><th>{{ t('courseGeneration.outlineReview.ideologyGoal', '育人目标') }}</th><th>{{ t('courseGeneration.outlineReview.ideologyMethod', '案例与实施方式') }}</th></tr></thead>
                    <tbody>
                      <tr v-if="!documentIdeologyCases.length"><td colspan="4">{{ t('courseGeneration.outlineReview.ideologyPending', '待教师结合具体讲次补充。') }}</td></tr>
                      <tr v-for="(item, index) in documentIdeologyCases" :key="index"><td><MathText :content="item.lecture || item.lesson || '—'" /></td><td><MathText :content="item.course_content || item.content || '—'" /></td><td><MathText :content="item.education_objective || item.objective || '—'" /></td><td><MathText :content="item.case || item.implementation || '—'" /></td></tr>
                    </tbody>
                  </table>
                </div>
              </section>

              <section class="formal-outline__template-section">
                <h2>{{ t('courseGeneration.outlineReview.templateReferences', '五、参考资料') }}</h2>
                <h3>{{ t('courseGeneration.outlineReview.templateReferenceBooks', '参考书籍') }}</h3>
                <ul v-if="documentReferenceBooks.length"><li v-for="item in documentReferenceBooks" :key="item"><MathText :content="item" /></li></ul>
                <p v-else>{{ t('courseGeneration.outlineReview.referencesPending', '暂无已确认参考书籍。') }}</p>
                <h3>{{ t('courseGeneration.outlineReview.templateWebResources', '网站资料') }}</h3>
                <ul v-if="documentReferenceWebsites.length"><li v-for="item in documentReferenceWebsites" :key="item"><MathText :content="item" /></li></ul>
                <p v-else>{{ t('courseGeneration.outlineReview.webReferencesPending', '暂无已确认网站资料。') }}</p>
              </section>

              <section class="formal-outline__template-section">
                <h2>{{ t('courseGeneration.outlineReview.templateCourseWebsite', '六、课程教学网站') }}</h2>
                <MathText tag="p" :content="documentCourseWebsite || t('courseGeneration.outlineReview.courseWebsitePending', '暂未确认课程教学网站。')" />
              </section>
            </template>
          </article>


          <p v-if="!blueprintNodes.length" class="outline-review__empty">
            {{ t('courseGeneration.outlineReview.empty', '目录尚未形成，请重新载入后再确认。') }}
          </p>
        </div>
      </template>

      <footer class="outline-review__footer" v-if="!isInline || (confirmationPlacement === 'internal' && requiresConfirmation) || (editable && dirty) || (confirmationPlacement === 'internal' && isInline && surface === 'teacher' && !editable) || actionError">
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
            v-if="!isInline || (confirmationPlacement === 'internal' && requiresConfirmation)"
            type="button"
            class="primary"
            :disabled="loading || acting || !!adjustmentProposal || !blueprintNodes.length"
            @click="confirmOutline"
          >
            <LoaderCircle v-if="confirming" :size="15" />
            <CircleCheck v-else :size="15" />
            {{ confirmationActionLabel }}
          </button>
        </div>
      </footer>
    </article>
    <span class="outline-review__sr-only" aria-live="polite">{{ liveStatus }}</span>
  </section>
</template>

<script setup lang="ts">
import DOMPurify from 'dompurify'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AlignCenter, AlignJustify, AlignLeft, AlignRight, ArrowRight, Bold, Braces, ChartNoAxesCombined, ChevronDown, ChevronUp, CircleCheck, Code2, FileText, FileType2, Heading2, Heading3, Highlighter, ImagePlus, IndentDecrease, IndentIncrease, Italic, Link2, List, ListOrdered, LoaderCircle, Minus, MoreHorizontal, Plus, Quote, Redo2, RemoveFormatting, Replace, Save, Search, Sigma, Sparkles, Strikethrough, Subscript, Superscript, Table2, TriangleAlert, Underline, Undo2, X } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import MarkdownRenderer from './MarkdownRenderer.vue'
import MathText from './MathText.vue'
import TextSelectionAiAction, { type TeacherInlineAiRequest } from './TextSelectionAiAction.vue'
import type { Node, Task } from '../stores/types'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { t } from '../shared/i18n'
import { renderMarkdown } from '../utils/markdown'
import { retrievalErrorTranslationKey } from '../utils/retrieval-errors'
import { createUuid } from '../utils/client-id'
import {
  inferredSessionsPerWeek,
  projectedLectureWeek,
  resolveTeachingWeekRange,
  zjuTeachingWeekRange,
} from '../utils/zju-academic-calendar'

type OutlineLessonType = {
  lessonUnitId: string
  value: string
  label?: string
}

type OutlineLessonTypeOption = {
  value: string
  label: string
}

const props = withDefaults(defineProps<{
  courseId: string
  courseName?: string
  nodes?: Node[]
  task?: Task
  surface?: 'student' | 'teacher'
  editable?: boolean
  variant?: 'full' | 'inline'
  requiresConfirmation?: boolean
  confirmationPlacement?: 'internal' | 'external'
  assistantOpen?: boolean
  requestBusy?: boolean
  lessonTypes?: OutlineLessonType[]
  lessonTypeOptions?: OutlineLessonTypeOption[]
  lessonTypeSavingId?: string
  lessonTypeError?: string
  lessonTypeErrorId?: string
}>(), {
  courseName: '',
  nodes: () => [],
  task: undefined,
  surface: 'student',
  editable: true,
  variant: 'full',
  requiresConfirmation: true,
  confirmationPlacement: 'internal',
  assistantOpen: false,
  requestBusy: false,
  lessonTypes: () => [],
  lessonTypeOptions: () => [],
  lessonTypeSavingId: '',
  lessonTypeError: '',
  lessonTypeErrorId: '',
})

const emit = defineEmits<{
  (event: 'confirmed'): void
  (event: 'open-ai'): void
  (event: 'open-ai-selection', value: TeacherInlineAiRequest): void
  (event: 'ai-candidate-change', candidate: Record<string, any> | null): void
  (event: 'ai-resolving', result: { accept: boolean }): void
  (event: 'ai-resolved', result: { accept: boolean }): void
  (event: 'ai-error', message: string): void
  (event: 'quality-review-change', report: Record<string, any>): void
  (event: 'lesson-type-change', result: { lessonUnitId: string; lessonType: string }): void
}>()

const courseStore = useCourseStore()
const workspace = useCourseWorkspaceStore()
const generationStore = useGenerationStore()
const blueprintDraft = ref<Record<string, any>>({})
const outlineRoot = ref<HTMLElement | null>(null)
const inlineAiAction = ref<{ openForDocument: (text?: string) => void } | null>(null)
const retrievalArtifact = ref<Record<string, any>>({})
// D-1：课程规格与覆盖度判定。只在后端真的给出判定时展示——没有判定时保持沉默，
// 而不是显示"完整"，因为"沉默被当成完整"正是这个问题的由来。
const coverageArtifact = ref<Record<string, any>>({})
const qualityArtifact = ref<Record<string, any>>({})
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
const targetQualityIssueCode = ref('')
const generatingProposal = ref(false)
const applyingProposal = ref(false)
const retryingRetrieval = ref(false)
const proposalNotice = ref('')
const liveStatus = ref('')
const proposalSummaryRef = ref<HTMLElement | null>(null)
const formalContractEditorRef = ref<HTMLElement | null>(null)
const chaptersRef = ref<HTMLElement | null>(null)
const richEditorRef = ref<HTMLElement | null>(null)
const insertControlRef = ref<HTMLElement | null>(null)
const moreControlRef = ref<HTMLElement | null>(null)
const findControlRef = ref<HTMLElement | null>(null)
const insertUrlInputRef = ref<HTMLInputElement | null>(null)
const findInputRef = ref<HTMLInputElement | null>(null)
const richEditorDirty = ref(false)
const editorMode = ref<'visual' | 'markdown'>('visual')
const markdownDraft = ref('')
const insertMenuOpen = ref(false)
const moreMenuOpen = ref(false)
const findPanelOpen = ref(false)
const findQuery = ref('')
const replaceQuery = ref('')
const findMatchCount = ref(0)
const findMatchIndex = ref(0)
const editorCharacterCount = ref(0)
const insertPrompt = ref<'link' | 'image' | 'formula' | ''>('')
const insertUrl = ref('')
let rememberedEditorRange: Range | null = null
const adjustmentRequestId = ref('')
const aiTargetNodeId = ref('')
const nodeAiInstruction = ref('')
const editHistory = ref<any[][]>([])
const editHistoryIndex = ref(-1)

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
const presentationDraft = computed<Record<string, any>>(() => adjustmentProposal.value?.draft || blueprintDraft.value)
const blueprintNodes = computed<any[]>(() => (
  Array.isArray(presentationDraft.value?.nodes)
    ? presentationDraft.value.nodes
    : Array.isArray(presentationDraft.value?.course_blueprint?.nodes)
      ? presentationDraft.value.course_blueprint.nodes
      : []
))
const canUndo = computed(() => editHistoryIndex.value > 0)
const canRedo = computed(() => editHistoryIndex.value >= 0 && editHistoryIndex.value < editHistory.value.length - 1)
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
  presentationDraft.value?.course_plan
  || presentationDraft.value?.course_outline
  || {}
))
const isLectureOutline = computed(() => {
  if (
    documentPlan.value.authoring_structure_version === 'lecture_v1'
    || blueprintDraft.value?.authoring_structure_version === 'lecture_v1'
    || blueprintDraft.value?.course_generation_brief?.course_shape_constraints?.teacher_lecture_mode
  ) return true
  const chapters = Array.isArray(documentPlan.value.chapters) ? documentPlan.value.chapters : []
  return chapters.length > 0 && chapters.every((chapter: any) => (
    Array.isArray(chapter?.sections) && chapter.sections.length === 1
  ))
})
const isLightOutline = computed(() => {
  if (!isLectureOutline.value) return false
  const taskStatus = String(props.task?.status || '')
  const taskPhase = String(props.task?.currentPhase || '')
  const detailStage = String(props.task?.phaseDetail?.stage || '')
  if (
    ['completed', 'completed_with_warnings'].includes(taskStatus)
    || taskPhase === 'teacher_outline_ready'
  ) return false
  return taskStatus === 'waiting_for_input'
    || taskPhase === 'outline_framework_ready'
    || detailStage === 'outline_framework_ready'
    || blueprintDraft.value?.outline_framework_only === true
})
const formalProfile = computed<Record<string, any>>(() => (
  blueprintDraft.value?.course_generation_brief?.formal_course_profile || {}
))
const teacherCourseBrief = computed<Record<string, any>>(() => (
  blueprintDraft.value?.course_generation_brief?.teacher_course_brief || {}
))
function formalList(value: unknown) {
  if (Array.isArray(value)) return value.map(item => String(item || '').trim()).filter(Boolean)
  return String(value || '').split(/\r?\n/).map(item => item.trim()).filter(Boolean)
}
function plainLectureTitle(value: unknown) {
  return String(value || '')
    .replace(/^(?:(?:第\s*)?\d+(?:\.\d+)?\s*[章节讲]\s*|\d+(?:\.\d+)+\s*)+/, '')
    .trim()
}
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
const documentIntroZh = computed(() => String(
  documentPlan.value.course_intro_zh
  || formalProfile.value.course_intro
  || documentPositioning.value
  || '',
).trim())
const documentIntroEn = computed(() => String(documentPlan.value.course_intro_en || '').trim())
const documentEducationObjectives = computed(() => formalList(documentPlan.value.education_objectives))
const documentMeasurableOutcomes = computed(() => formalList(documentPlan.value.measurable_outcomes))
const documentOutcomeAlignment = computed(() => (
  Array.isArray(documentPlan.value.outcome_alignment)
    ? documentPlan.value.outcome_alignment
      .filter((item: any) => item && typeof item === 'object')
      .map((item: any) => {
        const outcomeNumber = Number(item.outcome_number || item.outcome_index || 0)
        return {
          outcomeNumber,
          outcome: documentMeasurableOutcomes.value[outcomeNumber - 1]
            || t('courseGeneration.outlineReview.outcomeAlignmentUnknown', '待确认成果'),
          objectiveRefs: formalList(item.objective_refs),
          lectureLabels: (Array.isArray(item.lecture_numbers) ? item.lecture_numbers : [])
            .map((number: any) => Number(number))
            .filter((number: number) => Number.isInteger(number) && number > 0)
            .map((number: number) => t('courseGeneration.outlineReview.lectureNumber', '第{number}讲').replace('{number}', String(number))),
          assessmentEvidence: formalList(item.assessment_evidence),
          coverageScope: String(item.coverage_scope || '').trim(),
        }
      })
    : []
))
const documentTeachingMethods = computed(() => {
  const explicit = formalList(documentPlan.value.teaching_methods)
  if (explicit.length) return explicit
  const labels: Record<string, string> = {
    classroom: t('courseGeneration.outlineReview.teachingClassroom', '线下课堂'),
    online: t('courseGeneration.outlineReview.teachingOnline', '在线教学'),
    blended: t('courseGeneration.outlineReview.teachingBlended', '混合式教学'),
    self_study: t('courseGeneration.outlineReview.teachingSelfStudy', '自主学习'),
  }
  const method = String(teacherCourseBrief.value.teaching_context || '').trim()
  return method ? [labels[method] || method] : []
})
const documentAssessmentMethods = computed(() => (
  formalList(documentPlan.value.assessment_methods).length
    ? formalList(documentPlan.value.assessment_methods)
    : formalList(formalProfile.value.assessment_method || teacherCourseBrief.value.course_assessment_plan)
))
const documentAssessmentPlan = computed(() => (
  (Array.isArray(documentPlan.value.assessment_plan) ? documentPlan.value.assessment_plan : [])
    .filter((item: any) => item && typeof item === 'object')
    .map((item: any) => ({
      item: String(item.item || item.name || '').trim(),
      categoryLabel: String(item.category || '') === 'summative'
        ? t('courseGeneration.outlineReview.assessmentSummative', '终结性评价')
        : t('courseGeneration.outlineReview.assessmentFormative', '过程性评价'),
      weight: Number(item.weight_percent || item.weight || 0),
      criteria: String(item.criteria || item.scoring_criteria || '').trim(),
      outcomes: (Array.isArray(item.outcome_numbers) ? item.outcome_numbers : [])
        .map((number: any) => Number(number))
        .filter((number: number) => Number.isInteger(number) && number > 0)
        .map((number: number) => t('courseGeneration.outlineReview.outcomeNumber', '成果{number}').replace('{number}', String(number))),
    }))
    .filter((item: any) => item.item)
))
const documentReferenceBooks = computed(() => formalList(documentPlan.value.reference_books))
const documentReferenceWebsites = computed(() => formalList(documentPlan.value.reference_websites))
const confirmedReferenceOptions = computed(() => [
  ...documentReferenceBooks.value.map(label => ({ label, type: 'book' })),
  ...documentReferenceWebsites.value.map(label => ({ label, type: 'website' })),
])
const documentCourseWebsite = computed(() => String(documentPlan.value.course_website || '').trim())
const documentIdeologyCases = computed<any[]>(() => (
  (Array.isArray(documentPlan.value.ideology_cases) ? documentPlan.value.ideology_cases : [])
    .map((item: any) => typeof item === 'string' ? { implementation: item } : item)
    .filter((item: any) => item && typeof item === 'object')
))
const documentAcademicTerm = computed(() => String(
  courseStore.currentCourse?.term
  || formalProfile.value.term
  || teacherCourseBrief.value.academic_term
  || '',
).trim())
const documentWeekRange = computed(() => resolveTeachingWeekRange(
  documentAcademicTerm.value,
  formalProfile.value.week_range_mode,
  formalProfile.value.active_week_start,
  formalProfile.value.active_week_end,
))
const documentCalendarBasis = computed(() => {
  const calendarRange = zjuTeachingWeekRange(documentAcademicTerm.value)
  if (!calendarRange || documentWeekRange.value.mode !== 'academic_calendar') return ''
  const template = t(
    'courseGeneration.outlineReview.calendarAutoBasis',
    '{term}学期 · 按浙大校历自动排为 {weeks} 个教学周',
  )
  return template
    .replace('{term}', calendarRange.term)
    .replace('{weeks}', String(calendarRange.weeks))
})
const documentLectureSchedule = computed(() => {
  const slots = (Array.isArray(formalProfile.value.schedule_slots) ? formalProfile.value.schedule_slots : [])
    .map((slot: any) => ({ weekday: Number(slot?.weekday || 0), period: Number(slot?.period || 0) }))
    .filter(slot => slot.weekday > 0 && slot.period > 0)
    .sort((left, right) => left.weekday - right.weekday || left.period - right.period)
  const sessions: Array<{ weekday: number; periods: number[] }> = []
  slots.forEach((slot) => {
    const previous = sessions[sessions.length - 1]
    const previousPeriod = previous?.periods[previous.periods.length - 1]
    if (previous && previousPeriod !== undefined && previous.weekday === slot.weekday && previousPeriod + 1 === slot.period) {
      previous.periods.push(slot.period)
    } else {
      sessions.push({ weekday: slot.weekday, periods: [slot.period] })
    }
  })
  const hasSchedule = sessions.length > 0
  const sessionPattern = hasSchedule ? sessions : [{ weekday: 0, periods: [] }]
  const weekRange = documentWeekRange.value
  const persistedWeekRangeMode = String(formalProfile.value.week_range_mode || '').trim()
  const hasLegacyCustomWeekRange = (
    !persistedWeekRangeMode
    && formalProfile.value.active_week_start != null
    && formalProfile.value.active_week_end != null
    && weekRange.mode === 'custom'
    && (weekRange.start !== 1 || weekRange.end !== 16)
  )
  const canProjectWeeks = (
    hasSchedule
    || weekRange.mode === 'academic_calendar'
    || persistedWeekRangeMode === 'custom'
    || hasLegacyCustomWeekRange
  )
  const plannedLectureCount = Math.max(
    1,
    Number(
      formalProfile.value.planned_lecture_count
      || teacherCourseBrief.value.lecture_count
      || documentChapters.value.length,
    ),
  )
  const sessionsPerWeek = hasSchedule
    ? sessions.length
    : inferredSessionsPerWeek(plannedLectureCount, weekRange)
  return documentChapters.value.map((chapter: any, index: number) => {
    const section = Array.isArray(chapter.sections) ? chapter.sections[0] || {} : {}
    const session = sessionPattern[index % sessionPattern.length] || { weekday: 0, periods: [] }
    const explicitWeek = Number(section.week || section.teaching_week || chapter.week || 0)
    const projectedWeek = canProjectWeeks
      ? projectedLectureWeek(index, weekRange, sessionsPerWeek)
      : null
    const week = explicitWeek > 0
      ? `第${explicitWeek}周`
      : projectedWeek
        ? `第${projectedWeek}周`
        : t('courseGeneration.outlineReview.calendarPending', '待排课')
    const explicitHours = Number(
      section.planned_hours
      || chapter.planned_hours
      || lectureContract(chapter).officialHours
      || 0,
    )
    const hours = explicitHours > 0
      ? explicitHours
      : hasSchedule
        ? session.periods.length
        : 0
    return {
      number: `第${index + 1}讲`,
      title: plainLectureTitle(chapter.title),
      week,
      hours: hours > 0
        ? (Number.isInteger(hours) ? String(hours) : String(Number(hours.toFixed(1))))
        : t('courseGeneration.outlineReview.calendarHoursPending', '待确认'),
      education: lectureContract(chapter).education.join('、'),
      teachingForm: lectureContract(chapter).teachingForm,
      mentor: lectureContract(chapter).mentor,
    }
  })
})
const formalObjectiveGroups = computed(() => [
  { label: t('courseGeneration.outlineReview.templateLearningGoals', '学习目标'), items: documentObjectives.value },
  { label: t('courseGeneration.outlineReview.templateEducationGoals', '育人目标'), items: documentEducationObjectives.value },
  { label: t('courseGeneration.outlineReview.templateMeasurableResults', '可测量结果'), items: documentMeasurableOutcomes.value },
])
function lectureEvidence(chapter: any) {
  const section = Array.isArray(chapter?.sections) ? chapter.sections[0] || {} : {}
  return {
    objective: String(section.learning_objective || chapter?.learning_objective || '').trim(),
    scope: String(section.scope_boundary || chapter?.scope_boundary || '').trim(),
    assessments: formalList(section.assessment || chapter?.assessment),
  }
}
function proposalNodeChange(nodeId: string) {
  const diff = adjustmentProposal.value?.diff || {}
  const moved = (diff.moved || []).find((item: any) => String(item.node_id || '') === nodeId)
  if (moved) return {
    kind: 'move',
    label: `${t('courseGeneration.outlineReview.diffMoved', '移动')} · ${moved.old_position || '原位置'} → ${moved.new_position || '新位置'}`,
  }
  const updated = (diff.updated || []).find((item: any) => String(item.node_id || '') === nodeId)
  if (updated) return {
    kind: 'update',
    label: `${t('courseGeneration.outlineReview.diffUpdated', '内容修改')} · ${changedFieldSummary(updated.changes)}`,
  }
  const removed = (diff.removed || []).find((item: any) => String(item.node_id || '') === nodeId)
  if (removed) return { kind: 'remove', label: t('courseGeneration.outlineReview.diffRemoved', '删除') }
  return null
}
function proposalNodeAttributes(nodeId: string) {
  const change = proposalNodeChange(nodeId)
  if (!change) return ''
  return ` class="ai-change-target" data-ai-change="${escapeEditorAttribute(change.kind)}" data-ai-change-label="${escapeEditorAttribute(change.label)}"`
}
const documentChapters = computed<any[]>(() => {
  const plannedChapters = Array.isArray(documentPlan.value.chapters) ? documentPlan.value.chapters : []
  const chapters = outlineGroups.value
    .filter(group => Boolean(group.chapter))
    .map((group, chapterIndex) => {
      const chapterNode = group.chapter!.node
      const plannedChapter = plannedChapters.find((item: any) => String(item.node_id || '') === String(chapterNode.node_id || ''))
        || plannedChapters[chapterIndex]
        || {}
      const plannedSections = Array.isArray(plannedChapter.sections) ? plannedChapter.sections : []
      return {
        ...plannedChapter,
        _node: chapterNode,
        node_id: chapterNode.node_id,
        chapter_number: chapterIndex + 1,
        title: isLectureOutline.value
          ? `第${chapterIndex + 1}讲 ${plainLectureTitle(chapterNode.node_name || plannedChapter.title)}`.trim()
          : chapterNode.node_name,
        learning_focus: chapterNode.learning_objective || plannedChapter.learning_focus || '',
        learning_objective: chapterNode.learning_objective || plannedChapter.learning_objective || '',
        sections: group.sections.map(({ node }, sectionIndex) => {
          const plannedSection = plannedSections.find((item: any) => String(item.node_id || '') === String(node.node_id || ''))
            || plannedSections[sectionIndex]
            || {}
          return {
            ...plannedSection,
            ...node,
            _node: node,
            section_number: isLectureOutline.value ? String(chapterIndex + 1) : `${chapterIndex + 1}.${sectionIndex + 1}`,
            title: isLectureOutline.value ? plainLectureTitle(node.node_name) : node.node_name,
          }
        }),
      }
    })
  if (chapters.length || !blueprintNodes.value.length) return chapters
  return blueprintNodes.value.map((node, chapterIndex) => ({
    _node: node,
    node_id: node.node_id,
    chapter_number: chapterIndex + 1,
    title: isLectureOutline.value
      ? `第${chapterIndex + 1}讲 ${plainLectureTitle(node.node_name)}`.trim()
      : node.node_name,
    learning_focus: node.learning_objective || '',
    learning_objective: node.learning_objective || '',
    sections: [],
  }))
})
function lectureContract(chapter: any) {
  const section = Array.isArray(chapter?.sections) ? chapter.sections[0] || {} : {}
  const source = {
    ...(chapter?._node || {}),
    ...chapter,
    ...(section?._node || {}),
    ...section,
  }
  const breakdown = source.hour_breakdown && typeof source.hour_breakdown === 'object'
    ? source.hour_breakdown
    : {}
  const lectureHours = Number(breakdown.classroom_lecture || 0)
  const practiceHours = Number(breakdown.classroom_practice || 0)
  const onlineHours = Number(breakdown.online_instruction || 0)
  const resources = (Array.isArray(source.extension_resources) ? source.extension_resources : [])
    .filter((item: any) => item && typeof item === 'object')
    .map((item: any) => {
      const location = [item.edition, item.locator].map((value: any) => String(value || '').trim()).filter(Boolean).join(' · ')
      const pending = item.verification_status === 'verified'
        ? ''
        : `（${t('courseGeneration.outlineReview.referencePending', '待核验')}）`
      return `${String(item.title || '').trim()}${location ? ` · ${location}` : ''}${pending}`
    })
    .filter(Boolean)
  const tasks = (Array.isArray(source.learning_tasks) ? source.learning_tasks : [])
    .filter((item: any) => item && typeof item === 'object' && String(item.task || '').trim())
    .map((item: any) => `${item.mode === 'online' ? t('courseGeneration.outlineReview.taskOnline', '线上') : t('courseGeneration.outlineReview.taskOffline', '线下')}：${String(item.task).trim()}${item.evidence ? `；${String(item.evidence).trim()}` : ''}`)
  const mentor = source.external_mentor && typeof source.external_mentor === 'object'
    ? [source.external_mentor.name, source.external_mentor.organization, source.external_mentor.role]
      .map((value: any) => String(value || '').trim()).filter(Boolean).join(' · ')
    : ''
  const teachingForm = onlineHours > 0 && lectureHours + practiceHours > 0
    ? t('courseGeneration.outlineReview.teachingBlended', '混合式教学')
    : onlineHours > 0
      ? t('courseGeneration.outlineReview.teachingOnline', '在线教学')
      : practiceHours > lectureHours
        ? t('courseGeneration.outlineReview.teachingPractice', '线下实践')
        : t('courseGeneration.outlineReview.teachingClassroom', '线下课堂')
  return {
    anchors: formalList(source.application_anchors),
    resources,
    tasks,
    education: formalList(source.education_objective_refs),
    mentor,
    teachingForm,
    officialHours: lectureHours + practiceHours + onlineHours,
    independentHours: (Array.isArray(source.learning_tasks) ? source.learning_tasks : [])
      .reduce((sum: number, item: any) => sum + Number(item?.estimated_hours || 0), 0),
    hours: `${lectureHours} / ${practiceHours} / ${onlineHours}`,
  }
}
const documentHourAllocation = computed(() => {
  const totals = documentChapters.value.reduce((result, chapter) => {
    const contract = lectureContract(chapter)
    const section = Array.isArray(chapter?.sections) ? chapter.sections[0] || {} : {}
    const breakdown = section.hour_breakdown || chapter.hour_breakdown || {}
    result.classroom += Number(breakdown.classroom_lecture || 0)
    result.practice += Number(breakdown.classroom_practice || 0)
    result.online += Number(breakdown.online_instruction || 0)
    result.independent += contract.independentHours
    return result
  }, { classroom: 0, practice: 0, online: 0, independent: 0 })
  return [
    { key: 'classroom', label: t('courseGeneration.outlineReview.hourClassroomLecture', '线下讲授'), hours: totals.classroom, counted: true },
    { key: 'practice', label: t('courseGeneration.outlineReview.hourClassroomPractice', '线下实践'), hours: totals.practice, counted: true },
    { key: 'online', label: t('courseGeneration.outlineReview.hourOnlineInstruction', '在线教学'), hours: totals.online, counted: true },
    { key: 'independent', label: t('courseGeneration.outlineReview.hourIndependentLearning', '课外学习负担'), hours: totals.independent, counted: false },
  ]
})
const documentCourseModules = computed(() => (
  (Array.isArray(documentPlan.value.course_modules) ? documentPlan.value.course_modules : [])
    .filter((item: any) => item && typeof item === 'object')
    .map((item: any, index: number) => {
      const numbers = (Array.isArray(item.lecture_numbers) ? item.lecture_numbers : [])
        .map((number: any) => Number(number))
        .filter((number: number) => Number.isInteger(number) && number > 0 && number <= documentChapters.value.length)
      return {
        id: String(item.module_id || `M${index + 1}`),
        title: String(item.title || item.name || '').trim(),
        lectures: numbers.map((number: number) => t('courseGeneration.outlineReview.lectureNumber', '第{number}讲').replace('{number}', String(number))),
        hours: numbers.reduce((sum: number, number: number) => sum + lectureContract(documentChapters.value[number - 1]).officialHours, 0),
      }
    })
    .filter((item: any) => item.title && item.lectures.length)
))
const assessmentPlanRows = computed<any[]>(() => (
  Array.isArray(documentPlan.value.assessment_plan) ? documentPlan.value.assessment_plan : []
))
const courseModuleRows = computed<any[]>(() => (
  Array.isArray(documentPlan.value.course_modules) ? documentPlan.value.course_modules : []
))

function inputValue(event: Event) {
  return String((event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement)?.value || '')
}

function ensureCoursePlan() {
  if (!blueprintDraft.value.course_plan || typeof blueprintDraft.value.course_plan !== 'object') {
    blueprintDraft.value.course_plan = clone(blueprintDraft.value.course_outline || {})
  }
  return blueprintDraft.value.course_plan as Record<string, any>
}

function markFormalChange() {
  actionError.value = ''
  liveStatus.value = t('courseGeneration.outlineReview.manualChanged', '大纲已修改，保存后生效')
}

function planListText(field: string) {
  return formalList(documentPlan.value[field]).join('\n')
}

function setPlanScalar(field: string, event: Event) {
  ensureCoursePlan()[field] = inputValue(event).trim()
  markFormalChange()
}

function setPlanList(field: string, event: Event) {
  ensureCoursePlan()[field] = inputValue(event).split(/\r?\n/).map(item => item.trim()).filter(Boolean)
  if (field === 'reference_books' || field === 'reference_websites') revalidateLectureResources()
  markFormalChange()
}

function ideologyCasesText() {
  const cases = Array.isArray(documentPlan.value.ideology_cases) ? documentPlan.value.ideology_cases : []
  return cases.map((item: any) => {
    if (typeof item === 'string') return item.trim()
    if (!item || typeof item !== 'object') return ''
    return [
      item.lecture || item.lesson,
      item.course_content || item.content,
      item.education_objective || item.objective,
      item.case || item.implementation,
    ].map(value => String(value || '').trim()).join(' ｜ ')
  }).filter(Boolean).join('\n')
}

function setIdeologyCases(event: Event) {
  ensureCoursePlan().ideology_cases = inputValue(event).split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => {
    const parts = line.split(/\s*[｜|]\s*/)
    if (parts.length < 4) return line
    return {
      lecture: parts[0],
      course_content: parts[1],
      education_objective: parts[2],
      implementation: parts.slice(3).join(' ｜ '),
    }
  })
  markFormalChange()
}

function numberList(value: unknown) {
  return Array.from(new Set(
    String(value || '').split(/[,\s，、;\uff1b]+/)
      .map(item => Number(item))
      .filter(item => Number.isInteger(item) && item > 0),
  ))
}

function numberListText(value: unknown) {
  return (Array.isArray(value) ? value : []).map(item => Number(item)).filter(Number.isFinite).join(',')
}

function outcomeAlignmentRow(index: number) {
  const rows = Array.isArray(documentPlan.value.outcome_alignment) ? documentPlan.value.outcome_alignment : []
  return rows.find((item: any) => Number(item?.outcome_number || item?.outcome_index || 0) === index + 1)
}

function outcomeAlignmentText(index: number, field: string) {
  const row = outcomeAlignmentRow(index) || {}
  if (field === 'lecture_numbers') return numberListText(row[field])
  if (Array.isArray(row[field])) return row[field].join('\n')
  return String(row[field] || '')
}

function setOutcomeAlignment(index: number, field: string, event: Event) {
  const plan = ensureCoursePlan()
  if (!Array.isArray(plan.outcome_alignment)) plan.outcome_alignment = []
  let row = outcomeAlignmentRow(index)
  if (!row) {
    row = { outcome_number: index + 1, objective_refs: [], lecture_numbers: [], assessment_evidence: [], coverage_scope: '' }
    plan.outcome_alignment.push(row)
  }
  const value = inputValue(event)
  if (field === 'lecture_numbers') row[field] = numberList(value)
  else if (field === 'objective_refs' || field === 'assessment_evidence') row[field] = value.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
  else row[field] = value.trim()
  markFormalChange()
}

function addAssessmentRow(category: 'formative' | 'summative') {
  const plan = ensureCoursePlan()
  if (!Array.isArray(plan.assessment_plan)) plan.assessment_plan = []
  plan.assessment_plan.push({ item: '', category, weight_percent: 0, criteria: '', outcome_numbers: [] })
  markFormalChange()
}

function setAssessmentField(index: number, field: string, event: Event) {
  const row = assessmentPlanRows.value[index]
  if (!row) return
  const value = inputValue(event)
  if (field === 'weight_percent') row[field] = Number(value || 0)
  else if (field === 'outcome_numbers') row[field] = numberList(value)
  else row[field] = value.trim()
  markFormalChange()
}

function removeAssessmentRow(index: number) {
  assessmentPlanRows.value.splice(index, 1)
  markFormalChange()
}

function addModuleRow() {
  const plan = ensureCoursePlan()
  if (!Array.isArray(plan.course_modules)) plan.course_modules = []
  const assigned = new Set(plan.course_modules.flatMap((item: any) => numberListText(item?.lecture_numbers).split(',').map(Number)))
  const remaining = documentChapters.value.map((_, index) => index + 1).filter(number => !assigned.has(number))
  plan.course_modules.push({ module_id: `M${plan.course_modules.length + 1}`, title: '', lecture_numbers: remaining })
  markFormalChange()
}

function setModuleField(index: number, field: string, event: Event) {
  const row = courseModuleRows.value[index]
  if (!row) return
  row[field] = field === 'lecture_numbers' ? numberList(inputValue(event)) : inputValue(event).trim()
  markFormalChange()
}

function removeModuleRow(index: number) {
  courseModuleRows.value.splice(index, 1)
  markFormalChange()
}

function lectureNode(index: number) {
  const chapter = documentChapters.value[index]
  const section = Array.isArray(chapter?.sections) ? chapter.sections[0] : null
  return section?._node || section || chapter?._node || chapter || null
}

function lectureChapterNode(index: number) {
  const chapter = documentChapters.value[index]
  return chapter?._node || chapter || null
}

function setLectureTitle(index: number, event: Event) {
  const title = plainLectureTitle(inputValue(event))
  const chapterNode = lectureChapterNode(index)
  const sectionNode = lectureNode(index)
  if (chapterNode) chapterNode.node_name = `第${index + 1}讲 ${title}`.trim()
  if (sectionNode) sectionNode.node_name = title
  markFormalChange()
}

function lectureListText(index: number, field: string) {
  return formalList(lectureNode(index)?.[field]).join('\n')
}

function setLectureList(index: number, field: string, event: Event) {
  const node = lectureNode(index)
  if (!node) return
  node[field] = inputValue(event).split(/\r?\n/).map(item => item.trim()).filter(Boolean)
  markFormalChange()
}

function lectureScalar(index: number, field: string) {
  return String(lectureNode(index)?.[field] || '')
}

function setLectureScalar(index: number, field: string, event: Event) {
  const node = lectureNode(index)
  if (!node) return
  node[field] = inputValue(event).trim()
  markFormalChange()
}

function lectureTasks(index: number) {
  const value = lectureNode(index)?.learning_tasks
  return Array.isArray(value) ? value : []
}

function addLectureTask(index: number) {
  const node = lectureNode(index)
  if (!node) return
  if (!Array.isArray(node.learning_tasks)) node.learning_tasks = []
  node.learning_tasks.push({ mode: 'offline', stage: 'after_class', task: '', evidence: '', estimated_hours: 0 })
  markFormalChange()
}

function setLectureTaskField(lectureIndex: number, taskIndex: number, field: string, event: Event) {
  const task = lectureTasks(lectureIndex)[taskIndex]
  if (!task) return
  task[field] = field === 'estimated_hours' ? Number(inputValue(event) || 0) : inputValue(event).trim()
  markFormalChange()
}

function removeLectureTask(lectureIndex: number, taskIndex: number) {
  lectureTasks(lectureIndex).splice(taskIndex, 1)
  markFormalChange()
}

function lectureResources(index: number) {
  const value = lectureNode(index)?.extension_resources
  return Array.isArray(value) ? value : []
}

function addLectureResource(index: number) {
  const node = lectureNode(index)
  if (!node) return
  if (!Array.isArray(node.extension_resources)) node.extension_resources = []
  node.extension_resources.push({ resource_type: 'other', title: '', edition: '', locator: '', source_ref: '', verification_status: 'pending' })
  markFormalChange()
}

function selectLectureResource(lectureIndex: number, resourceIndex: number, event: Event) {
  const resource = lectureResources(lectureIndex)[resourceIndex]
  if (!resource) return
  const label = inputValue(event)
  const option = confirmedReferenceOptions.value.find(item => item.label === label)
  resource.source_ref = label
  resource.title = label
  resource.resource_type = option?.type || 'other'
  resource.verification_status = option ? 'verified' : 'pending'
  markFormalChange()
}

function setLectureResourceField(lectureIndex: number, resourceIndex: number, field: string, event: Event) {
  const resource = lectureResources(lectureIndex)[resourceIndex]
  if (!resource) return
  resource[field] = inputValue(event).trim()
  markFormalChange()
}

function removeLectureResource(lectureIndex: number, resourceIndex: number) {
  lectureResources(lectureIndex).splice(resourceIndex, 1)
  markFormalChange()
}

function revalidateLectureResources() {
  const confirmed = new Set(confirmedReferenceOptions.value.map(item => item.label))
  documentChapters.value.forEach((_, index) => {
    lectureResources(index).forEach((resource: any) => {
      resource.verification_status = confirmed.has(String(resource.source_ref || '')) ? 'verified' : 'pending'
    })
  })
}

function lectureHour(index: number, field: string) {
  return Number(lectureNode(index)?.hour_breakdown?.[field] || 0)
}

function setLectureHour(index: number, field: string, event: Event) {
  const node = lectureNode(index)
  if (!node) return
  if (!node.hour_breakdown || typeof node.hour_breakdown !== 'object') node.hour_breakdown = {}
  node.hour_breakdown[field] = Number(inputValue(event) || 0)
  node.planned_hours = ['classroom_lecture', 'classroom_practice', 'online_instruction']
    .reduce((sum, key) => sum + Number(node.hour_breakdown[key] || 0), 0)
  markFormalChange()
}

function lectureMentor(index: number, field: string) {
  return String(lectureNode(index)?.external_mentor?.[field] || '')
}

function setLectureMentor(index: number, field: string, event: Event) {
  const node = lectureNode(index)
  if (!node) return
  if (!node.external_mentor || typeof node.external_mentor !== 'object') node.external_mentor = {}
  node.external_mentor[field] = inputValue(event).trim()
  markFormalChange()
}

function coursePlanFieldLabel(field: string) {
  const labels: Record<string, string> = {
    course_intro_zh: t('courseGeneration.outlineReview.templateChineseIntro', '中文简介'),
    course_intro_en: t('courseGeneration.outlineReview.templateEnglishIntro', '英文简介'),
    positioning: t('courseGeneration.outlineReview.positioning', '课程定位'),
    learning_objectives: t('courseGeneration.outlineReview.templateLearningGoals', '学习目标'),
    education_objectives: t('courseGeneration.outlineReview.templateEducationGoals', '育人目标'),
    measurable_outcomes: t('courseGeneration.outlineReview.templateMeasurableResults', '可测量结果'),
    outcome_alignment: t('courseGeneration.outlineReview.outcomeAlignmentTitle', '课程目标与预期成果关联表'),
    teaching_methods: t('courseGeneration.outlineReview.templateTeachingMethods', '授课方式'),
    assessment_plan: t('courseGeneration.outlineReview.templateAssessmentMethods', '考核方式'),
    course_modules: t('courseGeneration.outlineReview.moduleGroupingTitle', '知识模块与讲次范围'),
    reference_books: t('courseGeneration.outlineReview.referenceBooks', '参考书籍'),
    reference_websites: t('courseGeneration.outlineReview.referenceWebsites', '网络资源'),
  }
  return labels[field] || field
}
function lessonTypeControlHtml(chapter: any, chapterIndex: number) {
  if (!isLectureOutline.value || !props.lessonTypes.length) return ''
  const nodeId = String(chapter?.node_id || chapter?._node?.node_id || '')
  const lesson = props.lessonTypes.find(item => item.lessonUnitId === nodeId)
    || props.lessonTypes[chapterIndex]
  if (!lesson?.lessonUnitId || !lesson.value) return ''

  const options = props.lessonTypeOptions.some(option => option.value === lesson.value)
    ? props.lessonTypeOptions
    : [{ value: lesson.value, label: lesson.label || lesson.value }, ...props.lessonTypeOptions]
  const lessonTitle = String(chapter?.title || '').trim()
  const selectLabel = t('courseWorkbench.outlineLessonTypes.selectLabel', '{lesson}的课型')
    .replace('{lesson}', lessonTitle)
  const saving = props.lessonTypeSavingId === lesson.lessonUnitId
  const disabled = Boolean(props.lessonTypeSavingId)
  const error = props.lessonTypeErrorId === lesson.lessonUnitId ? props.lessonTypeError : ''
  const statusId = `lesson-type-status-${lesson.lessonUnitId.replace(/[^a-zA-Z0-9_-]/g, '-')}`
  const status = saving
    ? `<span id="${statusId}" class="outline-lesson-type-control__status" role="status">${escapeEditorText(t('courseWorkbench.outlineLessonTypes.saving', '正在保存'))}</span>`
    : error
      ? `<span id="${statusId}" class="outline-lesson-type-control__error" role="alert">${escapeEditorText(error)}</span>`
      : ''
  const optionHtml = options.map(option => (
    `<option value="${escapeEditorAttribute(option.value)}"${option.value === lesson.value ? ' selected' : ''}>${escapeEditorText(option.label)}</option>`
  )).join('')

  return `<span class="outline-lesson-type-control${saving ? ' is-saving' : ''}${error ? ' has-error' : ''}" contenteditable="false" data-lesson-type-control="true"><select data-lesson-type-select="true" data-lesson-unit-id="${escapeEditorAttribute(lesson.lessonUnitId)}" aria-label="${escapeEditorAttribute(selectLabel)}"${status ? ` aria-describedby="${statusId}"` : ''}${disabled ? ' disabled aria-disabled="true"' : ''}>${optionHtml}</select>${status}</span>`
}

const outlineEditorHtml = computed(() => documentChapters.value.map((chapter: any, chapterIndex: number) => {
  const chapterNode = chapter._node || chapter
  const chapterId = escapeEditorAttribute(String(chapterNode.node_id || outlineNodeId('chapter')))
  const chapterTitle = editorFieldHtml(
    chapterNode,
    'title_html',
    isLectureOutline.value ? chapter.title : chapterNode.node_name || chapter.title,
  )
  const chapterBody = editorBodyHtml(chapterNode, chapterNode.learning_objective || chapter.learning_focus)
  const chapterChange = proposalNodeAttributes(String(chapterNode.node_id || ''))
  const sections = (chapter.sections || []).map((section: any) => {
    const sectionNode = section._node || section
    const sectionId = escapeEditorAttribute(String(sectionNode.node_id || outlineNodeId('section')))
    const sectionTitle = editorFieldHtml(
      sectionNode,
      'title_html',
      isLectureOutline.value ? section.title || plainLectureTitle(chapter.title) : sectionNode.node_name || section.title,
    )
    const sectionBody = editorBodyHtml(
      sectionNode,
      isLectureOutline.value
        ? sectionNode.content_summary || section.content_summary || sectionNode.learning_objective
        : sectionNode.learning_objective,
    )
    const sectionChange = proposalNodeAttributes(String(sectionNode.node_id || ''))
    const collapsed = isLectureOutline.value || chapter.sections.length === 1
      ? ' data-collapsed-single-section="true" aria-hidden="true"'
      : ''
    const singleBody = isLectureOutline.value || chapter.sections.length === 1
      ? ' data-single-section-body="true"'
      : ''
    return `<h3 data-node-id="${sectionId}"${sectionChange}${collapsed}>${sectionTitle}</h3><div data-node-body="${sectionId}"${sectionChange}${singleBody}>${sectionBody}</div>`
  }).join('')
  const chapterBodyVisibility = isLectureOutline.value && chapter.sections?.length
    ? ' data-lecture-meta-body="true" hidden'
    : ''
  const lessonTypeControl = lessonTypeControlHtml(chapter, chapterIndex)
  const headingLabel = lessonTypeControl && !props.editable
    ? ` aria-label="${escapeEditorAttribute(String(chapter.title || '').trim())}"`
    : ''
  return `<h2 data-node-id="${chapterId}"${chapterChange}${headingLabel}>${chapterTitle}${lessonTypeControl}</h2><div data-node-body="${chapterId}"${chapterChange}${chapterBodyVisibility}>${chapterBody}</div>${sections}`
}).join(''))
const documentVisibleSectionCount = computed(() => documentChapters.value.reduce(
  (total, chapter) => {
    const count = Array.isArray(chapter.sections) ? chapter.sections.length : 0
    return total + (count > 1 ? count : 0)
  },
  0,
))
const confirmationActionLabel = computed(() => (
  props.surface === 'teacher'
    ? t('courseWorkbench.confirmOutline', '确认课程大纲')
    : t('courseGeneration.gate.confirmOutline', '确认目录并继续')
))
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
  course_plan: documentPlan.value,
  nodes: blueprintNodes.value.map(node => ({
    node_id: node.node_id,
    parent_node_id: node.parent_node_id,
    node_name: node.node_name,
    node_level: node.node_level,
    learning_objective: node.learning_objective || '',
    scope_boundary: node.scope_boundary || '',
    assessment: node.assessment || [],
    content_summary: node.content_summary || '',
    key_points: node.key_points || [],
    key_difficulties: node.key_difficulties || [],
    activities: node.activities || [],
    homework: node.homework || [],
    application_anchors: node.application_anchors || [],
    extension_resources: node.extension_resources || [],
    learning_tasks: node.learning_tasks || [],
    education_objective_refs: node.education_objective_refs || [],
    ideology_implementation: node.ideology_implementation || '',
    external_mentor: node.external_mentor || {},
    hour_breakdown: node.hour_breakdown || {},
    prerequisite_node_ids: node.prerequisite_node_ids || [],
    outline_editor_html: node.outline_editor_html || {},
  })),
}))
const dirty = computed(() => richEditorDirty.value || Boolean(baseline.value && draftSignature.value !== baseline.value))

onMounted(() => {
  document.addEventListener('selectionchange', rememberEditorSelection)
  document.addEventListener('pointerdown', closeEditorOverlaysOnOutsidePointer)
  void loadBlueprint()
})
onBeforeUnmount(() => {
  document.removeEventListener('selectionchange', rememberEditorSelection)
  document.removeEventListener('pointerdown', closeEditorOverlaysOnOutsidePointer)
})
watch(() => props.courseId, (courseId, previous) => {
  if (courseId && courseId !== previous) void loadBlueprint()
})
watch(() => props.editable, editable => {
  if (!editable) {
    syncActiveEditorToNodes()
    editorMode.value = 'visual'
    closeEditorOverlays()
    rememberedEditorRange = null
    aiTargetNodeId.value = ''
    nodeAiInstruction.value = ''
  }
})
watch(outlineEditorHtml, () => {
  void nextTick(refreshEditorStats)
}, { immediate: true })

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

function setQualityReview(report: Record<string, any> | null | undefined) {
  qualityArtifact.value = clone(report || {})
  emit('quality-review-change', clone(qualityArtifact.value))
}

const EDITOR_ALLOWED_TAGS = [
  'a', 'b', 'strong', 'em', 'i', 'u', 's', 'mark', 'sup', 'sub', 'br', 'p', 'div', 'h2', 'h3', 'ul', 'ol', 'li',
  'blockquote', 'span', 'img', 'figure', 'figcaption', 'table', 'thead', 'tbody',
  'tr', 'th', 'td', 'pre', 'code', 'hr',
]
const EDITOR_ALLOWED_ATTR = [
  'href', 'target', 'rel', 'src', 'alt', 'title', 'colspan', 'rowspan', 'data-language',
  'data-align', 'data-indent', 'data-formula', 'data-title-format', 'data-node-id', 'data-node-body',
]

function escapeEditorText(value: unknown) {
  const element = document.createElement('span')
  element.textContent = String(value || '')
  return element.innerHTML
}

function escapeEditorAttribute(value: string) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/`/g, '&#96;')
}

function sanitizeEditorHtml(value: unknown) {
  return String(DOMPurify.sanitize(String(value || ''), {
    ALLOWED_TAGS: EDITOR_ALLOWED_TAGS,
    ALLOWED_ATTR: EDITOR_ALLOWED_ATTR,
  }))
}

function editorPlainText(value: unknown) {
  const element = document.createElement('div')
  element.innerHTML = sanitizeEditorHtml(value)
  const blocks = Array.from(element.querySelectorAll('p, li, blockquote, div'))
    .map(item => String(item.textContent || '').replace(/\s+/g, ' ').trim())
    .filter(Boolean)
  return (blocks.length ? blocks.join('\n') : String(element.textContent || ''))
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function normalizedEditorText(value: unknown) {
  return String(value || '').replace(/\s+/g, ' ').trim()
}

function editorFieldHtml(node: Record<string, any>, field: 'title_html' | 'body_html', plainValue: unknown) {
  const stored = sanitizeEditorHtml(node?.outline_editor_html?.[field])
  if (stored && normalizedEditorText(editorPlainText(stored)) === normalizedEditorText(plainValue)) return stored
  return escapeEditorText(plainValue)
}

function editorBodyHtml(node: Record<string, any>, plainValue: unknown) {
  const stored = sanitizeEditorHtml(node?.outline_editor_html?.body_html)
  if (stored) return /<(?:p|div|ul|ol|blockquote|table|pre|figure|hr)\b/i.test(stored) ? stored : `<p>${stored}</p>`
  const fallback = escapeEditorText(plainValue)
  return fallback ? `<p>${fallback}</p>` : '<p><br></p>'
}

function editorLearningObjective(value: unknown, fallback: unknown = '') {
  const element = document.createElement('div')
  element.innerHTML = sanitizeEditorHtml(value)
  const candidate = Array.from(element.querySelectorAll('p, li, blockquote'))
    .find(item => !item.closest('table, pre') && String(item.textContent || '').trim())
  const text = String(candidate?.textContent || '').replace(/\s+/g, ' ').trim()
  return text || String(fallback || '').trim()
}

function safeEditorInsertUrl(value: unknown) {
  try {
    const parsed = new URL(String(value || '').trim())
    return ['https:', 'http:'].includes(parsed.protocol) ? parsed.toString() : ''
  } catch {
    return ''
  }
}

function markdownTable(element: HTMLElement) {
  const rows = Array.from(element.querySelectorAll('tr')).map(row => (
    Array.from(row.querySelectorAll(':scope > th, :scope > td'))
      .map(cell => String(cell.textContent || '').replace(/\|/g, '\\|').replace(/\s+/g, ' ').trim())
  )).filter(row => row.length)
  if (!rows.length) return ''
  const width = Math.max(...rows.map(row => row.length))
  const normalized = rows.map(row => [...row, ...Array(Math.max(0, width - row.length)).fill('')])
  const header = normalized[0]!
  const body = normalized.slice(1)
  return [
    `| ${header.join(' | ')} |`,
    `| ${header.map(() => '---').join(' | ')} |`,
    ...body.map(row => `| ${row.join(' | ')} |`),
  ].join('\n')
}

function htmlNodeToMarkdown(node: ChildNode): string {
  if (node.nodeType === 3) return String(node.textContent || '')
  if (!(node instanceof HTMLElement)) return ''
  const tag = node.tagName.toLowerCase()
  const inner = Array.from(node.childNodes).map(htmlNodeToMarkdown).join('')
  const formula = String(node.dataset.formula || '').trim()
  if (formula) return `$${formula.replace(/\$/g, '\\$')}$`
  if (tag === 'br') return '\n'
  if (tag === 'strong' || tag === 'b') return `**${inner}**`
  if (tag === 'em' || tag === 'i') return `*${inner}*`
  if (tag === 'u') return `<u>${inner}</u>`
  if (tag === 's') return `~~${inner}~~`
  if (tag === 'mark' || tag === 'sup' || tag === 'sub') return `<${tag}>${inner}</${tag}>`
  if (tag === 'code' && node.parentElement?.tagName.toLowerCase() !== 'pre') return `\`${inner.replace(/`/g, '\\`')}\``
  if (tag === 'a') {
    const href = safeEditorInsertUrl(node.getAttribute('href'))
    return href ? `[${inner || href}](${href})` : inner
  }
  if (tag === 'img') {
    const src = safeEditorInsertUrl(node.getAttribute('src'))
    const alt = String(node.getAttribute('alt') || t('courseGeneration.outlineReview.imageAlt', '大纲图片')).replace(/[\[\]]/g, '')
    return src ? `![${alt}](${src})` : ''
  }
  if (tag === 'p') {
    const align = ['left', 'center', 'right', 'justify'].includes(String(node.dataset.align || ''))
      ? ` data-align="${node.dataset.align}"`
      : ''
    const indent = /^[1-4]$/.test(String(node.dataset.indent || ''))
      ? ` data-indent="${node.dataset.indent}"`
      : ''
    return align || indent
      ? `<p${align}${indent}>${inner.trim()}</p>\n\n`
      : `${inner.trim()}\n\n`
  }
  if (tag === 'blockquote') return `${inner.trim().split('\n').map(line => `> ${line}`).join('\n')}\n\n`
  if (tag === 'ul' || tag === 'ol') {
    const items = Array.from(node.children).filter(item => item.tagName.toLowerCase() === 'li')
    const list = items.map((item, index) => `${tag === 'ol' ? `${index + 1}.` : '-'} ${Array.from(item.childNodes).map(htmlNodeToMarkdown).join('').trim()}`).join('\n')
    const extras = Array.from(node.childNodes)
      .filter(child => !(child instanceof HTMLElement) || child.tagName.toLowerCase() !== 'li')
      .map(htmlNodeToMarkdown)
      .join('')
      .trim()
    return `${list}${extras ? `\n\n${extras}` : ''}\n\n`
  }
  if (tag === 'pre') {
    const language = String(node.dataset.language || '').trim()
    return `\`\`\`${language}\n${String(node.textContent || '').trim()}\n\`\`\`\n\n`
  }
  if (tag === 'table') return `${markdownTable(node)}\n\n`
  if (tag === 'hr') return '---\n\n'
  return inner
}

function htmlToMarkdown(value: unknown) {
  const element = document.createElement('div')
  element.innerHTML = sanitizeEditorHtml(value)
  return Array.from(element.childNodes)
    .map(htmlNodeToMarkdown)
    .join('')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function outlineNodesToMarkdown() {
  if (isLectureOutline.value) {
    return documentChapters.value.map((chapter: any, chapterIndex: number) => {
      const section = Array.isArray(chapter.sections) ? chapter.sections[0] || {} : {}
      const sectionNode = section._node || section
      const title = String(chapter.title || `第${chapterIndex + 1}讲`).replace(/\s+/g, ' ').trim()
      const cachedMarkdown = String(sectionNode?.outline_editor_html?.body_markdown || '').trim()
      const body = cachedMarkdown || htmlToMarkdown(editorBodyHtml(
        sectionNode,
        sectionNode.content_summary || section.content_summary || sectionNode.learning_objective,
      ))
      return `## ${title}${body ? `\n\n${body}` : ''}`
    }).join('\n\n').trim()
  }
  return blueprintNodes.value.map(node => {
    const level = Number(node.node_level || 2) === 1 ? '##' : '###'
    const title = String(node.node_name || '').replace(/\s+/g, ' ').trim()
    const cachedMarkdown = String(node?.outline_editor_html?.body_markdown || '').trim()
    const body = cachedMarkdown || htmlToMarkdown(editorBodyHtml(node, node.learning_objective))
    return `${level} ${title}${body ? `\n\n${body}` : ''}`
  }).join('\n\n').trim()
}

function markdownHeadingText(value: unknown) {
  const element = document.createElement('div')
  element.innerHTML = renderMarkdown(String(value || ''))
  return String(element.textContent || value || '').replace(/\s+/g, ' ').trim()
}

function markdownToEditorHtml(value: unknown) {
  let source = String(value || '')
  source = source.replace(/\$\$([\s\S]+?)\$\$/g, (_match, formula) => {
    const normalized = String(formula || '').trim()
    return `<p data-align="center"><span data-formula="${escapeEditorAttribute(normalized)}">${escapeEditorText(normalized)}</span></p>`
  })
  source = source.replace(/(?<!\\)\$([^$\n]+?)\$/g, (_match, formula) => {
    const normalized = String(formula || '').trim()
    return `<span data-formula="${escapeEditorAttribute(normalized)}">${escapeEditorText(normalized)}</span>`
  })
  return sanitizeEditorHtml(renderMarkdown(source))
}

function markdownSegments(value: string) {
  const segments: Array<{ level: 1 | 2; title: string; body: string }> = []
  let active: { level: 1 | 2; title: string; lines: string[] } | null = null
  let fence = ''
  for (const line of value.replace(/\r\n?/g, '\n').split('\n')) {
    const fenceMatch = line.match(/^\s*(```+|~~~+)/)
    const fenceToken = fenceMatch?.[1] || ''
    if (fenceToken) fence = fence ? (fence[0] === fenceToken[0] ? '' : fence) : fenceToken
    const heading = !fence ? line.match(/^\s{0,3}(#{1,3})\s+(.+?)\s*#*\s*$/) : null
    const headingMarks = heading?.[1] || ''
    const headingTitle = heading?.[2] || ''
    if (headingMarks && headingTitle) {
      if (active) segments.push({ level: active.level, title: active.title, body: active.lines.join('\n').trim() })
      active = {
        level: headingMarks.length >= 3 ? 2 : 1,
        title: markdownHeadingText(headingTitle),
        lines: [],
      }
      continue
    }
    if (active) active.lines.push(line)
  }
  if (active) segments.push({ level: active.level, title: active.title, body: active.lines.join('\n').trim() })
  return segments.filter(segment => segment.title)
}

function syncMarkdownToNodes() {
  const segments = markdownSegments(markdownDraft.value)
  if (!segments.some(segment => segment.level === 1)) {
    actionError.value = t('courseGeneration.outlineReview.chapterRequiredMarkdown', 'Markdown 中至少需要一个 ## 章标题。')
    return false
  }
  if (isLectureOutline.value) {
    if (segments.some(segment => segment.level !== 1)) {
      actionError.value = t(
        'courseGeneration.outlineReview.lectureMarkdownHeadings',
        '讲次式大纲只使用 ## 讲次标题，每个标题下直接编辑讲次简介。',
      )
      return false
    }
    const currentChapters = documentChapters.value
    const usedChapterIds = new Set<string>()
    const parsed = segments.flatMap((segment, index) => {
      const normalizedTitle = normalizedEditorText(plainLectureTitle(segment.title))
      const matched = currentChapters.find((chapter: any) => (
        !usedChapterIds.has(String(chapter.node_id || ''))
        && normalizedEditorText(plainLectureTitle(chapter.title)) === normalizedTitle
      )) || currentChapters[index]
      const chapterNode = matched?._node || {}
      const matchedSection = Array.isArray(matched?.sections) ? matched.sections[0] || {} : {}
      const sectionNode = matchedSection._node || matchedSection
      const chapterId = String(chapterNode.node_id || outlineNodeId('chapter'))
      const sectionId = String(sectionNode.node_id || outlineNodeId('section'))
      const lectureTitle = `第${index + 1}讲 ${plainLectureTitle(segment.title)}`.trim()
      const sectionTitle = plainLectureTitle(segment.title)
      const bodyHtml = markdownToEditorHtml(segment.body)
      usedChapterIds.add(chapterId)
      return [{
        ...clone(chapterNode),
        node_id: chapterId,
        parent_node_id: String(chapterNode.parent_node_id || 'root'),
        node_name: lectureTitle,
        node_level: 1,
        prerequisite_node_ids: Array.isArray(chapterNode.prerequisite_node_ids) ? chapterNode.prerequisite_node_ids : [],
        outline_editor_html: {
          ...(chapterNode.outline_editor_html || {}),
          title_html: escapeEditorText(lectureTitle),
        },
      }, {
        ...clone(sectionNode),
        node_id: sectionId,
        parent_node_id: chapterId,
        node_name: sectionTitle,
        node_level: 2,
        content_summary: editorPlainText(bodyHtml).trim(),
        prerequisite_node_ids: Array.isArray(sectionNode.prerequisite_node_ids) ? sectionNode.prerequisite_node_ids : [],
        outline_editor_html: {
          ...(sectionNode.outline_editor_html || {}),
          title_html: escapeEditorText(sectionTitle),
          body_html: bodyHtml,
          body_markdown: segment.body,
        },
      }]
    })
    const keptIds = new Set(parsed.map(node => String(node.node_id || '')))
    parsed.forEach(node => {
      node.prerequisite_node_ids = node.prerequisite_node_ids.filter((id: string) => keptIds.has(String(id)))
    })
    replaceBlueprintNodes(parsed)
    recordEditHistory()
    richEditorDirty.value = false
    actionError.value = ''
    return true
  }
  const existing = blueprintNodes.value
  const usedIds = new Set<string>()
  let currentChapterId = ''
  const parsed = segments.map((segment, index) => {
    let level = segment.level
    if (level === 2 && !currentChapterId) level = 1
    const matched = existing.find(node => (
      !usedIds.has(String(node.node_id || ''))
      && Number(node.node_level || 2) === level
      && normalizedEditorText(node.node_name) === normalizedEditorText(segment.title)
    )) || existing.find(node => !usedIds.has(String(node.node_id || '')) && Number(node.node_level || 2) === level)
    const nodeId = String(matched?.node_id || outlineNodeId(level === 1 ? 'chapter' : 'section'))
    usedIds.add(nodeId)
    if (level === 1) currentChapterId = nodeId
    const bodyHtml = markdownToEditorHtml(segment.body)
    return {
      ...clone(matched || {}),
      node_id: nodeId,
      parent_node_id: level === 1 ? String(matched?.parent_node_id || 'root') : currentChapterId,
      node_name: segment.title,
      node_level: level,
      learning_objective: editorLearningObjective(bodyHtml, matched?.learning_objective),
      prerequisite_node_ids: Array.isArray(matched?.prerequisite_node_ids) ? matched.prerequisite_node_ids : [],
      outline_editor_html: {
        ...(matched?.outline_editor_html || {}),
        title_html: escapeEditorText(segment.title),
        body_html: bodyHtml,
        body_markdown: segment.body,
      },
      _markdown_index: index,
    }
  }).map(({ _markdown_index, ...node }) => node)
  const keptIds = new Set(parsed.map(node => String(node.node_id || '')))
  parsed.forEach(node => {
    node.prerequisite_node_ids = node.prerequisite_node_ids.filter((id: string) => keptIds.has(String(id)))
  })
  replaceBlueprintNodes(parsed)
  recordEditHistory()
  richEditorDirty.value = false
  actionError.value = ''
  return true
}

async function setEditorMode(mode: 'visual' | 'markdown') {
  if (mode === editorMode.value || adjustmentBusy.value) return
  closeEditorOverlays()
  if (mode === 'markdown') {
    if (!syncRichEditorToNodes()) return
    markdownDraft.value = outlineNodesToMarkdown()
  } else if (richEditorDirty.value && !syncMarkdownToNodes()) {
    return
  }
  editorMode.value = mode
  rememberedEditorRange = null
  await nextTick()
  refreshEditorStats()
}

function handleMarkdownInput() {
  richEditorDirty.value = true
  refreshEditorStats()
  markManualChange(t('courseGeneration.outlineReview.manualChanged', '大纲已修改，保存后生效'))
}

function isLessonTypeControlTarget(target: EventTarget | null) {
  return target instanceof Element && Boolean(target.closest('[data-lesson-type-control]'))
}

function handleLessonTypeControlChange(event: Event) {
  const target = event.target
  if (!(target instanceof HTMLSelectElement) || !target.matches('[data-lesson-type-select]')) return
  const lessonUnitId = String(target.dataset.lessonUnitId || '')
  const lessonType = String(target.value || '')
  if (!lessonUnitId || !lessonType) return
  emit('lesson-type-change', { lessonUnitId, lessonType })
}

function handleRichEditorInput(event?: Event) {
  if (isLessonTypeControlTarget(event?.target || null)) return
  richEditorDirty.value = true
  refreshEditorStats()
  if (findPanelOpen.value && findQuery.value) refreshFindMatches(false)
  markManualChange(t('courseGeneration.outlineReview.manualChanged', '大纲已修改，保存后生效'))
}

function refreshEditorStats() {
  const value = editorMode.value === 'markdown'
    ? markdownDraft.value
    : editorTextWithoutLessonTypeControls()
  editorCharacterCount.value = value.replace(/\s/g, '').length
}

function editorTextWithoutLessonTypeControls() {
  const editor = richEditorRef.value
  if (!editor) return editorPlainText(outlineEditorHtml.value)
  const snapshot = editor.cloneNode(true) as HTMLElement
  snapshot.querySelectorAll('[data-lesson-type-control]').forEach(control => control.remove())
  return String(snapshot.textContent || '')
}

function selectionBelongsToEditor() {
  const selection = window.getSelection()
  return Boolean(selection?.anchorNode && richEditorRef.value?.contains(selection.anchorNode))
}

function rememberEditorSelection() {
  const selection = window.getSelection()
  if (!selection?.rangeCount || !selectionBelongsToEditor()) return
  rememberedEditorRange = selection.getRangeAt(0).cloneRange()
}

function normalizeNestedEditorHeadings() {
  const editor = richEditorRef.value
  if (!editor) return
  editor.querySelectorAll<HTMLElement>('[data-node-body] h2, [data-node-body] h3').forEach(heading => {
    const body = heading.closest<HTMLElement>('[data-node-body]')
    if (!body || body.parentElement !== editor) return
    const trailingNodes: ChildNode[] = []
    let sibling = heading.nextSibling
    while (sibling) {
      trailingNodes.push(sibling)
      sibling = sibling.nextSibling
    }
    const nextBody = document.createElement('div')
    nextBody.dataset.nodeBody = String(heading.dataset.nodeId || outlineNodeId('body'))
    trailingNodes.forEach(node => nextBody.appendChild(node))
    if (!nextBody.childNodes.length) nextBody.innerHTML = '<p><br></p>'
    body.parentNode?.insertBefore(heading, body.nextSibling)
    body.parentNode?.insertBefore(nextBody, heading.nextSibling)
    if (!body.textContent?.trim() && !body.querySelector('img, ul, ol')) body.innerHTML = '<p><br></p>'
  })
}

function restoreEditorSelection() {
  const editor = richEditorRef.value
  if (!editor) return false
  const selection = window.getSelection()
  const savedRange = selectionBelongsToEditor() && selection?.rangeCount
    ? selection.getRangeAt(0).cloneRange()
    : rememberedEditorRange
  editor.focus({ preventScroll: true })
  if (savedRange) {
    selection?.removeAllRanges()
    selection?.addRange(savedRange)
    return true
  }
  const range = document.createRange()
  range.selectNodeContents(editor)
  range.collapse(false)
  selection?.removeAllRanges()
  selection?.addRange(range)
  return true
}

function runEditorCommand(command: string, value?: string) {
  const editor = richEditorRef.value
  if (!editor || !props.editable || adjustmentBusy.value) return
  restoreEditorSelection()
  const commandValue = command === 'formatBlock' && value ? `<${value}>` : value
  if (typeof document.execCommand === 'function') document.execCommand(command, false, commandValue)
  rememberEditorSelection()
  normalizeNestedEditorHeadings()
  handleRichEditorInput()
}

function selectedEditorBlocks() {
  const editor = richEditorRef.value
  if (!editor || !restoreEditorSelection()) return [] as HTMLElement[]
  const selection = window.getSelection()
  if (!selection?.rangeCount) return [] as HTMLElement[]
  const range = selection.getRangeAt(0)
  const blocks = Array.from(editor.querySelectorAll<HTMLElement>('h2, h3, p, li, blockquote, pre, td, th'))
    .filter(block => {
      try {
        return range.intersectsNode(block)
      } catch {
        return false
      }
    })
  if (blocks.length) return blocks
  const anchor = selection.anchorNode instanceof HTMLElement
    ? selection.anchorNode
    : selection.anchorNode?.parentElement
  const block = anchor?.closest<HTMLElement>('h2, h3, p, li, blockquote, pre, td, th')
  return block && editor.contains(block) ? [block] : []
}

function editorFormattingTarget(block: HTMLElement) {
  if (!['h2', 'h3'].includes(block.tagName.toLowerCase())) return block
  let target = block.querySelector<HTMLElement>(':scope > [data-title-format]')
  if (target) return target
  target = document.createElement('span')
  target.dataset.titleFormat = 'true'
  while (block.firstChild) target.appendChild(block.firstChild)
  block.appendChild(target)
  return target
}

function applyEditorAlignment(alignment: 'left' | 'center' | 'right' | 'justify') {
  selectedEditorBlocks().forEach(block => {
    const target = editorFormattingTarget(block)
    if (alignment === 'left') delete target.dataset.align
    else target.dataset.align = alignment
  })
  moreMenuOpen.value = false
  rememberEditorSelection()
  handleRichEditorInput()
}

function adjustEditorIndent(delta: -1 | 1) {
  selectedEditorBlocks().forEach(block => {
    const target = editorFormattingTarget(block)
    const current = Number(target.dataset.indent || 0)
    const nextValue = Math.max(0, Math.min(4, current + delta))
    if (nextValue) target.dataset.indent = String(nextValue)
    else delete target.dataset.indent
  })
  moreMenuOpen.value = false
  rememberEditorSelection()
  handleRichEditorInput()
}

function highlightEditorSelection() {
  if (!restoreEditorSelection()) return
  const selection = window.getSelection()
  if (!selection?.rangeCount || selection.isCollapsed) return
  const range = selection.getRangeAt(0)
  let applied = false
  if (typeof document.execCommand === 'function') {
    applied = document.execCommand('hiliteColor', false, '#fff0a8')
      || document.execCommand('backColor', false, '#fff0a8')
  }
  richEditorRef.value?.querySelectorAll<HTMLElement>('[style*="background"]').forEach(element => {
    const mark = document.createElement('mark')
    while (element.firstChild) mark.appendChild(element.firstChild)
    element.replaceWith(mark)
    applied = true
  })
  if (!applied) {
    const mark = document.createElement('mark')
    try {
      mark.appendChild(range.extractContents())
      range.insertNode(mark)
    } catch {
      return
    }
  }
  moreMenuOpen.value = false
  rememberEditorSelection()
  handleRichEditorInput()
}

function clearEditorFormatting() {
  const blocks = selectedEditorBlocks()
  if (typeof document.execCommand === 'function') document.execCommand('removeFormat', false)
  blocks.forEach(block => {
    const target = block.matches('[data-title-format]')
      ? block
      : block.querySelector<HTMLElement>(':scope > [data-title-format]') || block
    delete target.dataset.align
    delete target.dataset.indent
  })
  moreMenuOpen.value = false
  rememberEditorSelection()
  handleRichEditorInput()
}

function applyEditorBlockStyle(event: Event) {
  const select = event.target as HTMLSelectElement
  runEditorCommand('formatBlock', select.value)
  select.value = 'p'
}

function insertEditorHtml(html: string) {
  const editor = richEditorRef.value
  if (!editor || !restoreEditorSelection()) return
  const safeHtml = sanitizeEditorHtml(html)
  const selection = window.getSelection()
  const range = selectionBelongsToEditor() && selection?.rangeCount
    ? selection.getRangeAt(0)
    : null
  if (range) {
    range.deleteContents()
    const fragment = range.createContextualFragment(safeHtml)
    const lastNode = fragment.lastChild
    range.insertNode(fragment)
    if (lastNode) {
      range.setStartAfter(lastNode)
      range.collapse(true)
      selection?.removeAllRanges()
      selection?.addRange(range)
    }
  } else {
    editor.insertAdjacentHTML('beforeend', safeHtml)
  }
  closeInsertControls()
  rememberEditorSelection()
  handleRichEditorInput()
}

function toggleInsertMenu() {
  rememberEditorSelection()
  moreMenuOpen.value = false
  closeFindPanel()
  insertPrompt.value = ''
  insertUrl.value = ''
  insertMenuOpen.value = !insertMenuOpen.value
}

function closeInsertControls() {
  insertMenuOpen.value = false
  insertPrompt.value = ''
  insertUrl.value = ''
}

function toggleMoreMenu() {
  rememberEditorSelection()
  closeInsertControls()
  closeFindPanel()
  moreMenuOpen.value = !moreMenuOpen.value
}

function closeFindPanel() {
  findPanelOpen.value = false
  findMatchCount.value = 0
  findMatchIndex.value = 0
}

async function toggleFindPanel() {
  rememberEditorSelection()
  closeInsertControls()
  moreMenuOpen.value = false
  findPanelOpen.value = !findPanelOpen.value
  if (!findPanelOpen.value) return
  await nextTick()
  findInputRef.value?.focus()
  findInputRef.value?.select()
  refreshFindMatches(true)
}

function closeEditorOverlays() {
  closeInsertControls()
  closeFindPanel()
  moreMenuOpen.value = false
}

function closeEditorOverlaysOnOutsidePointer(event: PointerEvent) {
  const target = event.target
  if (!(target instanceof globalThis.Node)) return
  if (!insertControlRef.value?.contains(target)) closeInsertControls()
  if (!moreControlRef.value?.contains(target)) moreMenuOpen.value = false
  if (!findControlRef.value?.contains(target)) closeFindPanel()
}

async function openInsertPrompt(type: 'link' | 'image' | 'formula') {
  rememberEditorSelection()
  moreMenuOpen.value = false
  closeFindPanel()
  insertMenuOpen.value = false
  insertPrompt.value = type
  insertUrl.value = ''
  await nextTick()
  insertUrlInputRef.value?.focus()
}

function confirmInsertPrompt() {
  if (insertPrompt.value === 'formula') {
    const formula = insertUrl.value.trim()
    if (!formula) return
    insertEditorHtml(`<span data-formula="${escapeEditorAttribute(formula)}">${escapeEditorText(formula)}</span>`)
    return
  }
  const url = safeEditorInsertUrl(insertUrl.value)
  if (!url) {
    actionError.value = t('courseGeneration.outlineReview.invalidInsertAddress', '请输入有效的 http 或 https 地址。')
    return
  }
  const escapedUrl = escapeEditorAttribute(url)
  if (insertPrompt.value === 'image') {
    insertEditorHtml(`<figure><img src="${escapedUrl}" alt="${escapeEditorAttribute(t('courseGeneration.outlineReview.imageAlt', '大纲图片'))}"><figcaption>${escapeEditorText(t('courseGeneration.outlineReview.imageCaption', '图片说明'))}</figcaption></figure><p><br></p>`)
    return
  }
  restoreEditorSelection()
  const selection = window.getSelection()
  if (selection && !selection.isCollapsed && typeof document.execCommand === 'function') {
    document.execCommand('createLink', false, url)
    const anchor = selection.anchorNode instanceof HTMLElement
      ? selection.anchorNode.closest('a')
      : selection.anchorNode?.parentElement?.closest('a')
    anchor?.setAttribute('target', '_blank')
    anchor?.setAttribute('rel', 'noopener noreferrer')
    closeInsertControls()
    handleRichEditorInput()
    return
  }
  insertEditorHtml(`<a href="${escapedUrl}" target="_blank" rel="noopener noreferrer">${escapeEditorText(url)}</a>`)
}

function insertEditorTable() {
  insertEditorHtml([
    '<table><thead><tr>',
    `<th>${escapeEditorText(t('courseGeneration.outlineReview.tableHeader', '标题'))} 1</th>`,
    `<th>${escapeEditorText(t('courseGeneration.outlineReview.tableHeader', '标题'))} 2</th>`,
    `<th>${escapeEditorText(t('courseGeneration.outlineReview.tableHeader', '标题'))} 3</th>`,
    '</tr></thead><tbody>',
    '<tr><td><br></td><td><br></td><td><br></td></tr>',
    '<tr><td><br></td><td><br></td><td><br></td></tr>',
    '</tbody></table><p><br></p>',
  ].join(''))
}

function insertEditorDiagram() {
  const source = 'flowchart LR\n  A[开始] --> B[学习活动]\n  B --> C[达成目标]'
  insertEditorHtml(`<pre data-language="mermaid"><code>${escapeEditorText(source)}</code></pre><p><br></p>`)
}

function insertEditorBlock(tag: 'blockquote' | 'pre') {
  closeInsertControls()
  runEditorCommand('formatBlock', tag)
}

function insertEditorDivider() {
  insertEditorHtml('<hr><p><br></p>')
}

function handleRichEditorPaste(event: ClipboardEvent) {
  if (!props.editable) return
  event.preventDefault()
  const html = event.clipboardData?.getData('text/html') || ''
  if (html) {
    const container = document.createElement('div')
    container.innerHTML = html
    container.querySelectorAll('h1, h2').forEach(heading => {
      const normalized = document.createElement('h2')
      normalized.innerHTML = heading.innerHTML
      heading.replaceWith(normalized)
    })
    container.querySelectorAll('h3, h4, h5, h6').forEach(heading => {
      const normalized = document.createElement('h3')
      normalized.innerHTML = heading.innerHTML
      heading.replaceWith(normalized)
    })
    container.querySelectorAll<HTMLElement>('*').forEach(element => {
      element.removeAttribute('class')
      element.removeAttribute('id')
      element.removeAttribute('style')
      element.removeAttribute('lang')
      element.removeAttribute('dir')
    })
    const safeHtml = sanitizeEditorHtml(container.innerHTML)
    if (safeHtml) {
      insertEditorHtml(safeHtml)
      normalizeNestedEditorHeadings()
      return
    }
  }
  const text = event.clipboardData?.getData('text/plain') || ''
  restoreEditorSelection()
  if (typeof document.execCommand === 'function') document.execCommand('insertText', false, text)
  handleRichEditorInput()
}

type EditorTextMatch = { node: Text; start: number; end: number }

function collectEditorTextMatches() {
  const editor = richEditorRef.value
  const query = findQuery.value.trim().toLocaleLowerCase()
  if (!editor || !query) return [] as EditorTextMatch[]
  const walker = document.createTreeWalker(editor, window.NodeFilter.SHOW_TEXT)
  const matches: EditorTextMatch[] = []
  let current = walker.nextNode()
  while (current) {
    const node = current as Text
    if (node.parentElement?.closest('[data-lesson-type-control]')) {
      current = walker.nextNode()
      continue
    }
    const value = String(node.nodeValue || '')
    const normalized = value.toLocaleLowerCase()
    let offset = 0
    while (offset <= normalized.length - query.length) {
      const index = normalized.indexOf(query, offset)
      if (index < 0) break
      matches.push({ node, start: index, end: index + query.length })
      offset = index + Math.max(1, query.length)
    }
    current = walker.nextNode()
  }
  return matches
}

function selectFindMatch(match: EditorTextMatch | undefined) {
  if (!match) return
  const selection = window.getSelection()
  const range = document.createRange()
  range.setStart(match.node, match.start)
  range.setEnd(match.node, match.end)
  selection?.removeAllRanges()
  selection?.addRange(range)
  match.node.parentElement?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
}

function refreshFindMatches(selectFirst = false) {
  const matches = collectEditorTextMatches()
  findMatchCount.value = matches.length
  if (!matches.length) {
    findMatchIndex.value = 0
    return
  }
  if (selectFirst || findMatchIndex.value >= matches.length) findMatchIndex.value = 0
  selectFindMatch(matches[findMatchIndex.value])
}

function stepFindMatch(delta: -1 | 1) {
  const matches = collectEditorTextMatches()
  findMatchCount.value = matches.length
  if (!matches.length) return
  findMatchIndex.value = (findMatchIndex.value + delta + matches.length) % matches.length
  selectFindMatch(matches[findMatchIndex.value])
}

function replaceCurrentMatch() {
  const matches = collectEditorTextMatches()
  const match = matches[findMatchIndex.value]
  if (!match) return
  const range = document.createRange()
  range.setStart(match.node, match.start)
  range.setEnd(match.node, match.end)
  range.deleteContents()
  range.insertNode(document.createTextNode(replaceQuery.value))
  handleRichEditorInput()
  refreshFindMatches(false)
  findInputRef.value?.focus()
}

function replaceAllMatches() {
  const query = findQuery.value.trim()
  if (!query) return
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const pattern = new RegExp(escaped, 'giu')
  const nodes = new Set(collectEditorTextMatches().map(match => match.node))
  nodes.forEach(node => {
    node.nodeValue = String(node.nodeValue || '').replace(pattern, () => replaceQuery.value)
  })
  handleRichEditorInput()
  refreshFindMatches(true)
  findInputRef.value?.focus()
}

function handleEditorKeydown(event: KeyboardEvent) {
  if (isLessonTypeControlTarget(event.target)) return
  const modifier = event.metaKey || event.ctrlKey
  const key = event.key.toLowerCase()
  if (modifier && key === 's') {
    event.preventDefault()
    void saveDraft()
    return
  }
  if (modifier && key === 'k') {
    event.preventDefault()
    void openInsertPrompt('link')
    return
  }
  if (modifier && key === 'f') {
    event.preventDefault()
    void toggleFindPanel()
    return
  }
  if (modifier && event.altKey && (key === '1' || key === '2')) {
    event.preventDefault()
    runEditorCommand('formatBlock', key === '1' ? 'h2' : 'h3')
    return
  }
  if (event.key === 'Escape') closeEditorOverlays()
}

function syncRichEditorToNodes() {
  const editor = richEditorRef.value
  if (!editor || !richEditorDirty.value) return true
  normalizeNestedEditorHeadings()
  const existingById = new Map(blueprintNodes.value.map(node => [String(node.node_id || ''), node]))
  const parsed: any[] = []
  let currentChapterId = ''
  let activeNode: any | null = null
  let bodyFragments: string[] = []
  const leadingFragments: string[] = []

  const flushBody = () => {
    if (!activeNode) return
    const bodyHtml = sanitizeEditorHtml(bodyFragments.join(''))
    if (isLectureOutline.value && Number(activeNode.node_level || 0) === 2) {
      activeNode.content_summary = editorPlainText(bodyHtml).trim()
    } else {
      activeNode.learning_objective = editorLearningObjective(bodyHtml, activeNode.learning_objective)
    }
    const editorHtml = {
      ...(activeNode.outline_editor_html || {}),
      body_html: bodyHtml,
    }
    delete editorHtml.body_markdown
    activeNode.outline_editor_html = editorHtml
    bodyFragments = []
  }

  Array.from(editor.childNodes).forEach(child => {
    const element = child instanceof HTMLElement ? child : null
    const tagName = element?.tagName.toLowerCase()
    if (tagName === 'h2' || tagName === 'h3') {
      flushBody()
      const titleSnapshot = element!.cloneNode(true) as HTMLElement
      titleSnapshot.querySelectorAll('[data-lesson-type-control]').forEach(control => control.remove())
      const nodeName = String(titleSnapshot.textContent || '').replace(/\s+/g, ' ').trim()
      if (!nodeName) {
        activeNode = null
        return
      }
      let level = tagName === 'h2' ? 1 : 2
      if (level === 2 && !currentChapterId) level = 1
      const nodeId = String(element?.dataset.nodeId || outlineNodeId(level === 1 ? 'chapter' : 'section'))
      const existing = existingById.get(nodeId) || {}
      activeNode = {
        ...clone(existing),
        node_id: nodeId,
        parent_node_id: level === 1 ? String(existing.parent_node_id || 'root') : currentChapterId,
        node_name: nodeName,
        node_level: level,
        learning_objective: String(existing.learning_objective || ''),
        prerequisite_node_ids: Array.isArray(existing.prerequisite_node_ids) ? existing.prerequisite_node_ids : [],
        outline_editor_html: {
          ...(existing.outline_editor_html || {}),
          title_html: sanitizeEditorHtml(titleSnapshot.innerHTML || nodeName),
          body_html: '',
        },
      }
      if (level === 1) currentChapterId = nodeId
      parsed.push(activeNode)
      if (parsed.length === 1 && leadingFragments.length) {
        bodyFragments.push(...leadingFragments)
        leadingFragments.length = 0
      }
      return
    }
    if (!activeNode) {
      if (element) leadingFragments.push(element.outerHTML)
      else if (child.textContent) leadingFragments.push(`<p>${escapeEditorText(child.textContent)}</p>`)
      return
    }
    if (element?.hasAttribute('data-node-body')) bodyFragments.push(element.innerHTML)
    else if (element) bodyFragments.push(element.outerHTML)
    else if (child.textContent) bodyFragments.push(`<p>${escapeEditorText(child.textContent)}</p>`)
  })
  flushBody()

  if (!parsed.some(node => Number(node.node_level || 2) === 1)) {
    actionError.value = isLectureOutline.value
      ? t('courseGeneration.outlineReview.lectureRequired', '大纲至少需要保留一讲。')
      : t('courseGeneration.outlineReview.chapterRequired', '大纲至少需要保留一个章标题。')
    return false
  }
  const keptIds = new Set(parsed.map(node => String(node.node_id || '')))
  parsed.forEach(node => {
    node.prerequisite_node_ids = (node.prerequisite_node_ids || []).filter((id: string) => keptIds.has(String(id)))
  })
  replaceBlueprintNodes(parsed)
  recordEditHistory()
  richEditorDirty.value = false
  actionError.value = ''
  return true
}

function syncActiveEditorToNodes() {
  return editorMode.value === 'markdown'
    ? (!richEditorDirty.value || syncMarkdownToNodes())
    : syncRichEditorToNodes()
}

function currentNodeSnapshot() {
  return clone(blueprintNodes.value)
}

function replaceBlueprintNodes(nodes: any[]) {
  if (Array.isArray(blueprintDraft.value?.nodes)) {
    blueprintDraft.value.nodes = clone(nodes)
    return
  }
  blueprintDraft.value.course_blueprint = {
    ...(blueprintDraft.value.course_blueprint || {}),
    nodes: clone(nodes),
  }
}

function resetEditHistory() {
  editHistory.value = [currentNodeSnapshot()]
  editHistoryIndex.value = 0
}

function recordEditHistory() {
  const snapshot = currentNodeSnapshot()
  const signature = JSON.stringify(snapshot)
  const current = editHistory.value[editHistoryIndex.value]
  if (current && JSON.stringify(current) === signature) return
  editHistory.value = editHistory.value.slice(0, editHistoryIndex.value + 1)
  editHistory.value.push(snapshot)
  editHistoryIndex.value = editHistory.value.length - 1
}

function restoreEditHistory(index: number) {
  const snapshot = editHistory.value[index]
  if (!snapshot) return
  replaceBlueprintNodes(snapshot)
  editHistoryIndex.value = index
  markManualChange(t('courseGeneration.outlineReview.manualChanged', '大纲已修改，保存后生效'))
}

function undoEdit() {
  if (canUndo.value) restoreEditHistory(editHistoryIndex.value - 1)
}

function redoEdit() {
  if (canRedo.value) restoreEditHistory(editHistoryIndex.value + 1)
}

function listText(value: unknown) {
  if (!Array.isArray(value)) return ''
  return value.map(item => String(item || '').trim()).filter(Boolean).join('；')
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
    setQualityReview(
      data.quality
      || data.draft?.course_outline_quality_report
      || data.current?.course_outline_quality_report
      || {},
    )
    blueprintDraft.value = clone(data.draft || data.current || data || {})
    richEditorDirty.value = false
    editorMode.value = 'visual'
    markdownDraft.value = ''
    closeInsertControls()
    rememberedEditorRange = null
    seedNodesFromCourse()
    if (!blueprintDraft.value.course_name) blueprintDraft.value.course_name = props.courseName
    syncNavigationFromDraft()
    baseline.value = draftSignature.value
    resetEditHistory()
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
    course_plan: draft.course_plan || draft.course_outline,
    nodes: draft.nodes,
    learning_asset_plan: draft.learning_asset_plan,
    blueprint_locks: draft.blueprint_locks || {},
  }
}

async function persistDraft(showMessage = true) {
  if (!blueprintNodes.value.length) return
  if (!syncActiveEditorToNodes()) throw new Error('invalid-outline-editor-document')
  const result = await workspace.saveBlueprint(props.courseId, draftPayload())
  if (result?.draft) blueprintDraft.value = clone(result.draft)
  setQualityReview(result?.quality_report || result?.draft?.course_outline_quality_report || {})
  richEditorDirty.value = false
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
      richEditorDirty.value = false
      editorMode.value = 'visual'
      markdownDraft.value = ''
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
    content_summary: t('courseGeneration.outlineReview.changedContentSummary', '内容要点'),
    application_anchors: t('courseGeneration.outlineReview.applicationAnchorLabel', '应用载体'),
    extension_resources: t('courseGeneration.outlineReview.extensionResourceLabel', '拓展资源'),
    learning_tasks: t('courseGeneration.outlineReview.learningTaskLabel', '学习任务'),
    hour_breakdown: t('courseGeneration.outlineReview.hourBreakdownLabel', '讲授 / 实践 / 在线'),
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

function outlineNodeId(prefix: string) {
  return `${prefix}-${createUuid()}`
}

function markManualChange(message: string) {
  invalidateProposal()
  proposalNotice.value = message
  liveStatus.value = message
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
      ...(targetQualityIssueCode.value
        ? { target_quality_issue_code: targetQualityIssueCode.value }
        : {}),
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
  targetQualityIssueCode.value = ''
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
    targetQualityIssueCode.value = ''
    emit('ai-candidate-change', null)
    blueprintDraft.value = clone(result?.draft || candidate)
    richEditorDirty.value = false
    editorMode.value = 'visual'
    markdownDraft.value = ''
    setQualityReview(result?.quality_report || result?.draft?.course_outline_quality_report || {})
    syncNavigationFromDraft()
    baseline.value = draftSignature.value
    resetEditHistory()
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

async function requestAiCandidate(instruction: string, qualityIssueCode = '') {
  aiTargetNodeId.value = ''
  nodeAiInstruction.value = ''
  targetQualityIssueCode.value = qualityIssueCode.trim()
  adjustmentInstruction.value = instruction.trim()
  return generateAdjustmentProposal()
}

function openInlineAi() {
  inlineAiAction.value?.openForDocument()
}

function requestQualityRepair(issue: Record<string, any>) {
  targetQualityIssueCode.value = String(issue.code || '').trim()
  const baseInstruction = String(issue.repair_instruction || '').trim()
  const nodeIds = Array.isArray(issue.node_ids)
    ? issue.node_ids.map((item: unknown) => String(item || '').trim()).filter(Boolean)
    : []
  return nodeIds.length
    ? `${baseInstruction}\n仅允许修改节点：${nodeIds.join('、')}。`
    : baseInstruction
}

function qualityIssueField(issue: Record<string, any>) {
  if (issue.repair_field === 'reference_books') return 'reference_books'
  const code = String(issue.code || '')
  const hasNodeTarget = Array.isArray(issue.node_ids) && issue.node_ids.length > 0
  if (code.includes('course_intro_zh')) return 'course_intro_zh'
  if (code.includes('course_intro_en')) return 'course_intro_en'
  if (code.includes('positioning')) return 'positioning'
  if (code.includes('education_objective')) return 'education_objectives'
  if (code.includes('measurable_outcome')) return 'measurable_outcomes'
  if (code.includes('outcome_alignment')) return 'outcome_alignment'
  if (code.includes('content_summary')) return 'content_summary'
  if (code.includes('scope')) return 'scope_boundary'
  if (code.includes('key_difficult')) return 'key_difficulties'
  if (code.includes('key_point')) return 'key_points'
  if (code.includes('activit')) return 'activities'
  if (code.includes('homework')) return 'homework'
  if (code.includes('assessment')) return hasNodeTarget ? 'assessment' : 'assessment_plan'
  if (code.includes('module')) return 'course_modules'
  if (code.includes('learning_task') || code.includes('online_task')) return 'learning_tasks'
  if (code.includes('extension_resource')) return 'extension_resources'
  if (code.includes('hour')) return 'hour_breakdown'
  if (code.includes('reference_website')) return 'reference_websites'
  if (code.includes('reference')) return 'reference_books'
  if (code.includes('course_outcome') || code.includes('learning_objective')) return hasNodeTarget ? 'learning_objective' : 'learning_objectives'
  return ''
}

async function focusQualityIssueEditor(issue: Record<string, any>) {
  if (!props.editable) return false
  await nextTick()
  const contractEditor = formalContractEditorRef.value
  if (!contractEditor) return false
  const nodeIds = new Set(
    (Array.isArray(issue.node_ids) ? issue.node_ids : [])
      .map((item: unknown) => String(item || '').trim())
      .filter(Boolean),
  )
  const lectureEditor = Array.from(
    contractEditor.querySelectorAll<HTMLDetailsElement>('[data-outline-node-id]'),
  ).find(item => nodeIds.has(String(item.dataset.outlineNodeId || '')))
  if (lectureEditor) lectureEditor.open = true
  await nextTick()
  const field = qualityIssueField(issue)
  const fieldRoot = field
    ? (issue.repair_field === 'reference_books' ? contractEditor.querySelector<HTMLElement>('[data-outline-field="reference_books"]') : lectureEditor?.querySelector<HTMLElement>(`[data-outline-field="${field}"]`)
      || contractEditor.querySelector<HTMLElement>(`[data-outline-field="${field}"]`))
    : lectureEditor
  const target = fieldRoot?.querySelector<HTMLElement>('textarea, input, select, button') || fieldRoot || contractEditor
  target.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  target.focus?.({ preventScroll: true })
  return true
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
    if (!actionError.value) actionError.value = t('courseGeneration.outlineReview.saveFailed', '目录修改保存失败，请检查后重试。')
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
    if (!actionError.value) actionError.value = t('courseGeneration.outlineReview.saveFailed', '目录修改保存失败，请检查后重试。')
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
  } catch (error: any) {
    actionError.value = String(
      error?.response?.data?.detail?.message
      || error?.response?.data?.detail
      || t('courseGeneration.gate.confirmFailed', '确认失败，请检查目录后重试。'),
    )
  } finally {
    confirming.value = false
  }
}

defineExpose({
  finishEditing,
  confirmOutline,
  requestAiCandidate,
  requestQualityRepair,
  focusQualityIssueEditor,
  resolveAiCandidate,
  focusAiCandidate,
  openInlineAi,
  canConfirm: computed(() => Boolean(blueprintNodes.value.length)),
  qualityReview: qualityArtifact,
  dirty,
  canUndo,
  canRedo,
  undoEdit,
  redoEdit,
})
</script>

<style scoped>
.outline-review {
  position:relative;
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
.outline-review__sheet.has-ai-candidate{grid-template-rows:auto minmax(0,1fr) auto}
.outline-candidate-notice{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:11px 18px;border-bottom:1px solid #d9ddf5;color:#4338ca;background:#f5f5ff}.outline-candidate-notice>div{min-width:0;display:flex;align-items:center;gap:9px}.outline-candidate-notice>div>span{display:grid;gap:2px}.outline-candidate-notice strong{font-size:14px}.outline-candidate-notice small{color:#676aa0;font-size:11px}.outline-candidate-notice nav{flex:none;display:flex;align-items:center;gap:6px}.outline-candidate-notice button{min-height:32px;display:inline-flex;align-items:center;gap:5px;padding:0 9px;border:1px solid #d0d1ee;border-radius:7px;color:#4f55a9;background:#fff;font-size:11px;font-weight:750;cursor:pointer}.outline-candidate-notice button.primary{border-color:#5148dc;color:#fff;background:#5148dc}.outline-candidate-notice button:hover:not(:disabled){border-color:#9692e8;color:#4338ca;background:#f8f7ff}.outline-candidate-notice button.primary:hover:not(:disabled){border-color:#433bc4;color:#fff;background:#433bc4}.outline-candidate-notice button:focus-visible{outline:3px solid rgba(91,84,232,.22);outline-offset:2px}.outline-candidate-notice button:disabled{opacity:.5;cursor:not-allowed}
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
.formal-outline--editing {
  display:flex;
  flex-direction:column;
}
.formal-outline--editing > :not(.outline-rich-editor):not(.outline-markdown-workspace):not(.formal-contract-editor) {
  display:none;
}
.formal-outline--editing > .outline-rich-editor,
.formal-outline--editing > .outline-markdown-workspace,
.formal-outline--editing > .formal-contract-editor { order:1; }
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
.formal-outline--light .formal-outline__masthead { border-bottom:1px solid #e7e9ef; }
.formal-outline--light .formal-outline__schedule { padding-top:24px; }
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
.formal-outline__schedule > header h2 { margin:0; color:#242d40; font-size:18px; line-height:1.35; letter-spacing:-.012em; }
.formal-outline__brief ol,
.formal-outline__brief ul { margin:15px 0 0; padding-left:22px; }
.formal-outline__brief li { margin:9px 0; padding-left:5px; color:#4f596d; font-size:13px; line-height:1.7; }
.formal-outline__brief > div > p { margin:15px 0 0; color:#737d8f; font-size:13px; line-height:1.7; }
.formal-outline__template-section {
  padding:34px clamp(18px,4vw,44px) 4px;
}
.formal-outline__template-section + .formal-outline__template-section {
  padding-top:28px;
}
.formal-outline__template-section h2,
.formal-outline__template-heading h2 {
  margin:0;
  color:#242d40;
  font-size:18px;
  line-height:1.4;
  letter-spacing:-.012em;
}
.formal-outline__template-section h3 {
  margin:20px 0 8px;
  color:#3b4559;
  font-size:14px;
  line-height:1.5;
}
.formal-outline__attachment-heading {
  display:flex;
  align-items:baseline;
  justify-content:space-between;
  gap:16px;
}
.formal-outline__attachment-heading h3 { flex:none; }
.formal-outline__attachment-heading small {
  color:#737d8f;
  font-size:11px;
  line-height:1.5;
  text-align:right;
}
.formal-outline__template-section p,
.formal-outline__template-section li {
  color:#596579;
  font-size:13px;
  line-height:1.75;
}
.formal-outline__template-section p { margin:0; }
.formal-outline__template-section ul { margin:8px 0 0; padding-left:22px; }
.formal-outline__template-heading {
  padding:34px clamp(18px,4vw,44px) 0;
}
.formal-outline__attachments {
  margin-top:30px;
  border-top:1px solid #e7e9ef;
}
.formal-outline__table-wrap { overflow-x:auto; margin-top:10px; }
.formal-outline__table-wrap table { width:100%; border-collapse:collapse; }
.formal-outline__table-wrap th,
.formal-outline__table-wrap td {
  min-width:88px;
  padding:10px 12px;
  border:1px solid #e1e5ec;
  color:#596579;
  font-size:12px;
  line-height:1.55;
  text-align:left;
  vertical-align:top;
}
.formal-outline__table-wrap th { color:#394357; background:#f7f8fb; font-weight:800; }
.formal-contract-editor {
  margin:28px clamp(18px,4vw,44px) 0;
  border-top:1px solid #dfe3e9;
  border-bottom:1px solid #dfe3e9;
}
.formal-contract-editor__heading {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:20px;
  padding:20px 0;
}
.formal-contract-editor__heading span { display:grid; gap:4px; }
.formal-contract-editor__heading strong { color:#263047; font-size:17px; }
.formal-contract-editor__heading small { color:#737d8f; font-size:13px; line-height:1.55; }
.formal-contract-editor__heading em {
  min-width:28px;
  height:28px;
  display:grid;
  place-items:center;
  border-radius:50%;
  color:#9a5b17;
  background:#fff3d8;
  font-size:13px;
  font-style:normal;
  font-weight:800;
}
.formal-contract-editor__body { display:grid; gap:30px; padding:2px 0 30px; }
.formal-contract-editor__body > section { display:grid; gap:14px; }
.formal-contract-editor__body h3 { margin:0; color:#303a50; font-size:16px; }
.formal-contract-editor__grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }
.formal-contract-editor label { display:grid; gap:7px; min-width:0; }
.formal-contract-editor label.wide,.formal-contract-editor .wide { grid-column:1 / -1; }
.formal-contract-editor label > span,.formal-contract-editor legend { color:#596478; font-size:13px; font-weight:700; }
.formal-contract-editor input,.formal-contract-editor textarea,.formal-contract-editor select {
  width:100%;
  min-width:0;
  box-sizing:border-box;
  border:1px solid #d8dce6;
  border-radius:8px;
  background:#fff;
  color:#273148;
  font:inherit;
  font-size:15px;
  line-height:1.55;
  padding:9px 11px;
}
.formal-contract-editor textarea { resize:vertical; }
.formal-contract-editor input:focus,.formal-contract-editor textarea:focus,.formal-contract-editor select:focus {
  outline:2px solid rgba(96,104,189,.18);
  border-color:#7379c8;
}
.formal-contract-editor button {
  min-height:34px;
  border:1px solid #d7dbe5;
  border-radius:8px;
  background:#fff;
  color:#4f55b5;
  font-weight:750;
  cursor:pointer;
}
.formal-contract-editor button:disabled { color:#a4aabc; background:#f5f6f8; cursor:not-allowed; }
.formal-contract-editor__section-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.formal-contract-editor__section-heading > div { display:flex; gap:8px; }
.formal-contract-editor__section-heading button { padding:6px 10px; }
.formal-contract-editor__rows { display:grid; gap:10px; }
.formal-contract-editor__row { display:grid; align-items:center; gap:8px; }
.formal-contract-editor__row > button { width:34px; padding:0; color:#9b3543; }
.formal-contract-editor__row--alignment { grid-template-columns:1.3fr 1fr .7fr 1fr 1fr; }
.formal-contract-editor__row--alignment > strong { font-size:14px; line-height:1.45; }
.formal-contract-editor__row--assessment { grid-template-columns:1fr .8fr 90px 1.5fr .8fr 34px; }
.formal-contract-editor__row--module { grid-template-columns:1fr 1.4fr 34px; }
.formal-contract-editor__row--task { grid-template-columns:100px 100px 1.4fr 1.2fr 100px 34px; }
.formal-contract-editor__row--resource { grid-template-columns:1.6fr 1fr 1fr 34px; }
.formal-contract-editor__add { width:max-content; padding:6px 10px; }
.formal-contract-editor__lecture { border-top:1px solid #edf0f4; }
.formal-contract-editor__lecture > summary { padding:14px 0; cursor:pointer; color:#3f4960; }
.formal-contract-editor__lecture > div { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; padding:2px 0 22px; }
.formal-contract-editor__hours { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin:0; padding:12px; border:1px solid #e0e3ea; border-radius:8px; }
.formal-contract-editor__hours legend { padding:0 6px; }
.formal-contract-editor__mentor { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
.formal-outline__schedule > header span {
  display:block;
  margin-bottom:5px;
  color:#565db4;
  font-size:11px;
  font-weight:800;
}
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
.formal-outline__lecture-evidence { margin:34px clamp(18px,4vw,44px) 0; padding-top:28px; border-top:1px solid #dfe3e9; }
.formal-outline__lecture-evidence > h3 { margin:0 0 18px; color:#263047; font-size:19px; line-height:1.4; }
.formal-outline__lecture-evidence > ol { margin:0; padding:0; list-style:none; }
.formal-outline__lecture-evidence > ol > li { padding:18px 0; border-top:1px solid #edf0f4; }
.formal-outline__lecture-evidence > ol > li:first-child { border-top:0; }
.formal-outline__lecture-evidence header { display:grid; grid-template-columns:52px minmax(0,1fr); gap:12px; align-items:baseline; }
.formal-outline__lecture-evidence header span { color:#6068bd; font-size:11px; font-weight:850; }
.formal-outline__lecture-evidence header strong { color:#2c364b; font-size:14px; line-height:1.45; }
.formal-outline__lecture-evidence dl { display:grid; gap:7px; margin:12px 0 0 64px; }
.formal-outline__lecture-evidence dl > div { display:grid; grid-template-columns:62px minmax(0,1fr); gap:10px; }
.formal-outline__lecture-evidence dt { color:#7b8495; font-size:11px; font-weight:750; line-height:1.65; }
.formal-outline__lecture-evidence dd { margin:0; color:#566175; font-size:11px; line-height:1.65; }
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

.outline-document-toolbar {
  position:sticky;
  z-index:7;
  top:0;
  min-height:56px;
  display:flex;
  align-items:center;
  gap:6px;
  padding:0 10px;
  border-bottom:1px solid #e1e5ec;
  color:#536176;
  background:rgba(255,255,255,.98);
  box-shadow:0 7px 18px rgba(30,41,59,.055);
  overflow:visible;
}
.outline-document-toolbar.is-locked{opacity:.62}.outline-document-toolbar.is-locked>*{pointer-events:none}
.outline-rich-editor :deep(.ai-change-target){position:relative;border-radius:5px;background:rgba(238,242,255,.82);box-shadow:0 0 0 1px rgba(99,102,241,.28)}.outline-rich-editor :deep(h2.ai-change-target),.outline-rich-editor :deep(h3.ai-change-target){padding-right:170px}.outline-rich-editor :deep(h2.ai-change-target::after),.outline-rich-editor :deep(h3.ai-change-target::after){position:absolute;top:50%;right:8px;max-width:155px;overflow:hidden;padding:4px 8px;transform:translateY(-50%);border:1px solid #c8c7f2;border-radius:999px;color:#4338ca;background:#fff;box-shadow:0 4px 12px rgba(67,56,202,.1);content:attr(data-ai-change-label);font-size:9.5px;font-weight:800;text-overflow:ellipsis;white-space:nowrap}.outline-rich-editor :deep([data-ai-change="remove"]){background:rgba(255,241,242,.88);box-shadow:0 0 0 1px rgba(220,97,112,.35)}.outline-rich-editor :deep([data-ai-change="remove"]::after){border-color:#f1c7cd;color:#b4233c}
.outline-document-toolbar__group { display:flex; flex:0 0 auto; align-items:center; gap:2px; }
.outline-document-toolbar > i { width:1px; height:22px; flex:0 0 auto; margin:0 2px; background:#e1e5ec; }
.outline-document-toolbar button {
  min-height:34px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:6px;
  padding:0 7px;
  border:1px solid transparent;
  border-radius:7px;
  color:#526077;
  background:transparent;
  font-size:11.5px;
  font-weight:720;
  cursor:pointer;
}
.outline-document-toolbar button.format-icon { width:34px; padding:0; }
.outline-document-toolbar button.format-icon > span,
.outline-block-style > span {
  position:absolute;
  width:1px;
  height:1px;
  overflow:hidden;
  clip:rect(0,0,0,0);
  white-space:nowrap;
}
.outline-document-toolbar button:hover:not(:disabled) { color:#3730a3; background:#f1f2f8; }
.outline-document-toolbar button:focus-visible { outline:2px solid #5b57e8; outline-offset:1px; }
.outline-document-toolbar button:disabled { color:#adb5c1; opacity:.62; cursor:not-allowed; }
.outline-document-toolbar button.danger:hover:not(:disabled) { color:#b42318; background:#fff2f0; }
.outline-editor-modes {
  flex:0 0 auto;
  display:flex;
  align-items:center;
  gap:2px;
  padding:3px;
  border:1px solid #e2e5ec;
  border-radius:9px;
  background:#f5f6f8;
}
.outline-editor-modes button { min-height:29px; padding-inline:9px; border-radius:6px; }
.outline-editor-modes button.is-active { color:#3730a3; background:#fff; box-shadow:0 1px 3px rgba(30,41,59,.11); }
.outline-block-style { position:relative; flex:0 0 auto; }
.outline-block-style select {
  width:92px;
  height:34px;
  padding:0 26px 0 10px;
  border:1px solid transparent;
  border-radius:7px;
  color:#445066;
  background-color:transparent;
  font-size:11.5px;
  font-weight:720;
  outline:none;
  cursor:pointer;
}
.outline-block-style select:hover { color:#3730a3; background-color:#f1f2f8; }
.outline-block-style select:focus-visible { outline:2px solid #5b57e8; outline-offset:1px; }
.outline-insert-control,
.outline-toolbar-control { position:relative; flex:0 0 auto; }
.outline-document-toolbar .outline-insert-trigger.is-active,
.outline-document-toolbar .outline-menu-trigger.is-active { color:#3730a3; background:#f1f2f8; }
.outline-insert-menu,
.outline-insert-prompt,
.outline-format-menu,
.outline-find-panel {
  position:absolute;
  z-index:20;
  top:42px;
  right:0;
  width:300px;
  padding:8px;
  border:1px solid #dfe3eb;
  border-radius:11px;
  background:#fff;
  box-shadow:0 18px 42px rgba(30,41,59,.18);
}
.outline-insert-menu { display:grid; grid-template-columns:1fr 1fr; gap:3px; }
.outline-document-toolbar .outline-insert-menu > button {
  min-height:54px;
  justify-content:flex-start;
  gap:9px;
  padding:8px 9px;
  text-align:left;
}
.outline-insert-menu > button > span { min-width:0; display:grid; gap:2px; }
.outline-insert-menu strong { color:#303a50; font-size:12px; }
.outline-insert-menu small { color:#8a93a3; font-size:10px; font-weight:500; }
.outline-insert-prompt { width:330px; padding:13px; }
.outline-insert-prompt label { display:grid; gap:6px; }
.outline-insert-prompt label > span { color:#4a5568; font-size:11px; font-weight:750; }
.outline-insert-prompt input { height:38px; padding:0 10px; border-color:#d6dbe5; background:#fff; font-size:12px; }
.outline-insert-prompt > div { display:flex; justify-content:flex-end; gap:6px; margin-top:10px; }
.outline-document-toolbar .outline-insert-prompt button { min-height:32px; border-color:#dfe3eb; }
.outline-document-toolbar .outline-insert-prompt button.primary { border-color:#454ca8; color:#fff; background:#454ca8; }
.outline-format-menu {
  right:auto;
  left:0;
  width:252px;
  display:grid;
  gap:8px;
  padding:12px;
}
.outline-format-menu section { display:grid; grid-template-columns:72px minmax(0,1fr); align-items:center; gap:8px; }
.outline-format-menu section > span { color:#7b8494; font-size:10px; font-weight:740; }
.outline-format-menu section > div { display:flex; align-items:center; gap:3px; }
.outline-document-toolbar .outline-format-menu section button { width:34px; min-height:32px; padding:0; border-color:#e7e9ee; }
.outline-document-toolbar .outline-format-menu__clear { width:100%; min-height:34px; justify-content:flex-start; border-top:1px solid #eceef2; border-radius:0; padding:8px 5px 0; }
.outline-format-menu__count { justify-self:end; margin-top:-32px; padding:9px 5px 0; color:#929aaa; font-size:10px; font-weight:620; font-variant-numeric:tabular-nums; }
.outline-find-panel {
  right:0;
  width:356px;
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  gap:9px 7px;
  padding:13px;
}
.outline-find-panel label { min-width:0; display:grid; gap:5px; }
.outline-find-panel label > span { color:#6e7889; font-size:10px; font-weight:760; }
.outline-find-panel label > div { height:36px; display:flex; align-items:center; gap:7px; padding:0 9px; border:1px solid #d9dee7; border-radius:7px; color:#7d8797; background:#fff; }
.outline-find-panel input { min-width:0; flex:1; height:30px; padding:0; border:0; box-shadow:none; color:#303a50; background:transparent; font-size:12px; }
.outline-find-panel input:focus { border:0; box-shadow:none; outline:none; }
.outline-find-panel small { color:#8b94a3; font-size:10px; white-space:nowrap; }
.outline-find-panel__navigation { display:flex; align-items:flex-end; gap:3px; }
.outline-document-toolbar .outline-find-panel__navigation button { width:34px; min-height:36px; padding:0; border-color:#dfe3eb; }
.outline-find-panel__actions { grid-column:1 / -1; display:flex; justify-content:flex-end; gap:5px; }
.outline-document-toolbar .outline-find-panel__actions button { min-height:31px; border-color:#dfe3eb; }
.outline-markdown-guide { display:flex; align-items:center; gap:6px; margin:0; color:#737d8f; font-size:11px; }
.outline-rich-editor {
  min-height:420px;
  padding-bottom:64px;
  caret-color:#4038c7;
  color:#30394c;
  outline:none;
}
.outline-rich-editor.is-editable { cursor:text; }
.outline-rich-editor.is-editable:focus { box-shadow:inset 3px 0 0 #deddf8; }
.outline-rich-editor :deep(h2) {
  margin:0;
  padding:27px 0 10px;
  color:#1d2639;
  font-size:21px;
  font-weight:820;
  line-height:1.4;
  letter-spacing:-.015em;
}
.outline-rich-editor :deep(.outline-lesson-type-control) {
  display:inline-flex;
  align-items:center;
  gap:8px;
  max-width:100%;
  margin-left:14px;
  color:#6661bb;
  font-size:13px;
  font-weight:700;
  letter-spacing:0;
  line-height:1;
  vertical-align:3px;
  white-space:nowrap;
}
.outline-rich-editor :deep(.outline-lesson-type-control select) {
  min-width:112px;
  min-height:32px;
  padding:0 28px 0 10px;
  border:1px solid #d7d8ee;
  border-radius:7px;
  color:#5551ad;
  background:#fbfbff;
  font:inherit;
  cursor:pointer;
  transition:border-color .16s ease,color .16s ease,background-color .16s ease,box-shadow .16s ease;
}
.outline-rich-editor :deep(.outline-lesson-type-control select:hover:not(:disabled)) {
  border-color:#aaa7df;
  color:#403b9d;
  background:#f6f5ff;
}
.outline-rich-editor :deep(.outline-lesson-type-control select:focus-visible) {
  border-color:#716ddb;
  outline:0;
  box-shadow:0 0 0 3px rgba(91,87,232,.14);
}
.outline-rich-editor :deep(.outline-lesson-type-control select:disabled) {
  color:#8d8aad;
  background:#f5f5fa;
  opacity:.72;
  cursor:wait;
}
.outline-rich-editor :deep(.outline-lesson-type-control.has-error select) {
  border-color:#d8a09a;
  color:#9d3d34;
  background:#fffafa;
}
.outline-rich-editor :deep(.outline-lesson-type-control__status),
.outline-rich-editor :deep(.outline-lesson-type-control__error) {
  display:inline-flex;
  align-items:center;
  color:#6965b9;
  font-size:13px;
  font-weight:650;
  line-height:1.35;
}
.outline-rich-editor :deep(.outline-lesson-type-control__status::before) {
  width:6px;
  height:6px;
  margin-right:5px;
  border-radius:50%;
  background:#716ddb;
  animation:lesson-type-saving 1s ease-in-out infinite alternate;
  content:"";
}
.outline-rich-editor :deep(.outline-lesson-type-control__error) {
  max-width:260px;
  color:#a33a31;
  white-space:normal;
}
@keyframes lesson-type-saving {
  to { opacity:.35; transform:scale(.72); }
}
@media (prefers-reduced-motion: reduce) {
  .outline-rich-editor :deep(.outline-lesson-type-control__status::before) { animation:none; }
}
.outline-rich-editor :deep(h3) {
  margin:22px 0 7px 28px;
  padding-top:18px;
  border-top:1px solid #edf0f4;
  color:#2c364b;
  font-size:15px;
  font-weight:760;
  line-height:1.5;
}
.outline-rich-editor :deep(h3[data-collapsed-single-section="true"]) { display:none; }
.outline-rich-editor :deep([data-node-body]) {
  margin:0 0 2px 28px;
  color:#626d80;
  font-size:13px;
  line-height:1.75;
}
.outline-rich-editor :deep([data-single-section-body="true"]) { margin-left:0; padding-bottom:22px; }
.outline-rich-editor :deep(h2 + [data-node-body]) { margin-left:0; color:#6c7688; }
.outline-rich-editor :deep([data-node-body] p) { min-height:1.75em; margin:0; }
.outline-rich-editor :deep([data-node-body] ul),
.outline-rich-editor :deep([data-node-body] ol) { margin:7px 0; padding-left:24px; }
.outline-rich-editor :deep([data-node-body] li) { margin:3px 0; padding-left:2px; }
.outline-rich-editor :deep(a) { color:#3f47a8; text-decoration:underline; text-underline-offset:2px; }
.outline-rich-editor :deep(mark) { padding:0 .08em; color:inherit; background:#fff0a8; }
.outline-rich-editor :deep([data-align="center"]) { text-align:center; }
.outline-rich-editor :deep([data-align="right"]) { text-align:right; }
.outline-rich-editor :deep([data-align="justify"]) { text-align:justify; text-justify:inter-ideograph; }
.outline-rich-editor :deep([data-title-format]) { display:block; }
.outline-rich-editor :deep([data-indent="1"]) { margin-left:2em; }
.outline-rich-editor :deep([data-indent="2"]) { margin-left:4em; }
.outline-rich-editor :deep([data-indent="3"]) { margin-left:6em; }
.outline-rich-editor :deep([data-indent="4"]) { margin-left:8em; }
.outline-rich-editor :deep([data-formula]) { display:inline-block; padding:1px 6px; border:1px solid #e0e3eb; border-radius:5px; color:#293249; background:#f8f9fb; font-family:"Cambria Math",KaTeX_Math,serif; font-size:1.05em; }
.outline-rich-editor :deep(blockquote) { margin:12px 0; padding:9px 14px; border:1px solid #e0e3f3; border-radius:7px; color:#536176; background:#f7f7fc; }
.outline-rich-editor :deep(pre) { overflow:auto; margin:12px 0; padding:13px 15px; border:1px solid #e1e5ec; border-radius:8px; color:#374151; background:#f7f8fa; font:12px/1.65 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; white-space:pre-wrap; }
.outline-rich-editor :deep(table) { width:100%; margin:14px 0; border-collapse:collapse; table-layout:fixed; color:#465166; }
.outline-rich-editor :deep(th),
.outline-rich-editor :deep(td) { min-width:70px; padding:8px 10px; border:1px solid #d9dee7; text-align:left; vertical-align:top; }
.outline-rich-editor :deep(th) { color:#303a50; background:#f4f5f8; font-weight:760; }
.outline-rich-editor :deep(figure) { margin:16px 0; text-align:center; }
.outline-rich-editor :deep(figure img) { max-width:100%; max-height:440px; border-radius:6px; }
.outline-rich-editor :deep(figcaption) { margin-top:6px; color:#8790a0; font-size:11px; }
.outline-rich-editor :deep(hr) { margin:22px 0; border:0; border-top:1px solid #dfe3e9; }
.outline-rich-editor.is-editable :deep(h2:hover),
.outline-rich-editor.is-editable :deep(h3:hover),
.outline-rich-editor.is-editable :deep([data-node-body]:hover) { background:#fafaff; }
.outline-markdown-workspace {
  min-height:520px;
  display:grid;
  grid-template-columns:minmax(0,1fr) minmax(0,1fr);
  margin:28px clamp(18px,4vw,44px) 0;
  overflow:hidden;
  border:1px solid #dfe3eb;
  border-radius:10px;
  background:#fff;
}
.outline-markdown-pane { min-width:0; display:grid; grid-template-rows:38px minmax(0,1fr); }
.outline-markdown-pane > span { display:flex; align-items:center; padding:0 14px; border-bottom:1px solid #e7eaf0; color:#707b8e; background:#f8f9fb; font-size:10px; font-weight:780; letter-spacing:.04em; }
.outline-markdown-pane--source { border-right:1px solid #dfe3eb; }
.outline-markdown-pane--source textarea {
  min-height:480px;
  padding:18px;
  border:0;
  border-radius:0;
  color:#2f394d;
  background:#fcfcfd;
  font:12px/1.75 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  resize:none;
}
.outline-markdown-pane--source textarea:hover { background:#fcfcfd; }
.outline-markdown-pane--source textarea:focus { border:0; box-shadow:inset 3px 0 0 #deddf8; }
.outline-markdown-preview { min-height:480px; overflow:auto; padding:18px 20px; color:#3d475a; font-size:12px; line-height:1.75; }
.outline-markdown-preview :deep(h1),
.outline-markdown-preview :deep(h2),
.outline-markdown-preview :deep(h3) { margin:1.25em 0 .55em; color:#20293b; line-height:1.4; }
.outline-markdown-preview :deep(h1:first-child),
.outline-markdown-preview :deep(h2:first-child),
.outline-markdown-preview :deep(h3:first-child) { margin-top:0; }
.outline-markdown-preview :deep(h2) { font-size:18px; }
.outline-markdown-preview :deep(h3) { font-size:14px; }
.outline-markdown-preview :deep(table) { width:100%; border-collapse:collapse; }
.outline-markdown-preview :deep(th),
.outline-markdown-preview :deep(td) { padding:7px 9px; border:1px solid #d9dee7; text-align:left; }
.outline-markdown-preview :deep(pre) { overflow:auto; padding:12px; border-radius:7px; background:#f5f6f8; }

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
.outline-review[data-variant="inline"] .outline-review__body { overflow:visible; background:#fff; }
.outline-review[data-variant="inline"] .formal-outline {
  width:100%;
  margin:0;
  padding:0 0 56px;
  background:#fff;
  box-shadow:none;
}
.outline-review[data-variant="inline"] .formal-outline__masthead {
  overflow:visible;
  padding:54px 64px 32px;
  border:0;
  border-radius:0;
  background:#fff;
  box-shadow:none;
}
.outline-review[data-variant="inline"] .formal-outline__masthead::after { display:none; }
.outline-review[data-variant="inline"] .formal-outline--light .formal-outline__masthead {
  padding-bottom:26px;
  border-bottom:1px solid #e7e9ef;
}
.outline-review[data-variant="inline"] .formal-outline__brief { padding-inline:64px; }
.outline-review[data-variant="inline"] .formal-outline__schedule { margin-inline:64px; padding-inline:0; }
.outline-review[data-variant="inline"] .formal-outline__schedule { padding-top:28px; }
.outline-review[data-variant="inline"] .outline-markdown-workspace { margin:28px 64px 0; }
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
  .outline-document-toolbar { gap:4px; padding-inline:8px; overflow-x:auto; overflow-y:visible; }
  .outline-document-toolbar > i { margin-inline:0; }
  .outline-block-style select { width:88px; }
  .outline-insert-menu,
  .outline-insert-prompt,
  .outline-format-menu,
  .outline-find-panel { position:fixed; top:auto; right:12px; bottom:12px; left:12px; width:auto; }
  .outline-markdown-guide { white-space:nowrap; }
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
  .outline-review[data-variant="inline"] .outline-markdown-workspace,
  .outline-markdown-workspace { grid-template-columns:1fr; margin:22px 12px 0; }
  .outline-markdown-pane--source { border-right:0; border-bottom:1px solid #dfe3eb; }
  .outline-markdown-pane--source textarea,
  .outline-markdown-preview { min-height:340px; }
  .outline-review[data-variant="inline"] .outline-review__chapters { padding:20px 14px 30px; }
  .formal-outline__masthead { padding:30px 24px 24px; }
  .formal-outline__masthead h1 { font-size:28px; }
  .formal-outline__masthead dl { gap:12px 20px; margin-top:22px; }
  .formal-outline__brief { grid-template-columns:1fr; padding:30px 12px; }
  .formal-outline__brief > div { padding:0; }
  .formal-outline__brief > div + div { margin-top:28px; padding:28px 0 0; border-top:1px solid #e7e9ef; border-left:0; }
  .formal-outline__schedule,.formal-outline__lecture-evidence { margin-inline:12px; padding-inline:0; }
  .formal-outline__schedule > header { align-items:flex-start; flex-direction:column; gap:8px; }
  .formal-outline__schedule > header p { text-align:left; }
  .formal-outline__chapter-block > header { grid-template-columns:32px minmax(0,1fr); gap:10px; }
  .formal-outline__chapter-block > header small { grid-column:2; }
  .formal-outline__chapter-block > ol { margin-left:42px; }
  .formal-outline__chapter-block > ol > li { grid-template-columns:1fr; gap:5px; }
  .formal-outline__lecture-evidence dl { margin-left:0; }
  .formal-outline__lecture-evidence dl > div { grid-template-columns:1fr; gap:2px; }
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
  .formal-outline { animation:none!important; }
}
</style>
