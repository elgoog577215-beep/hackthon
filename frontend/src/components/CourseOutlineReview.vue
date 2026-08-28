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

          <div
            v-if="editable"
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
                  <option value="h2">{{ t('courseGeneration.outlineReview.chapterHeading', '章标题') }}</option>
                  <option value="h3">{{ t('courseGeneration.outlineReview.sectionHeading', '小节标题') }}</option>
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
              <Heading2 :size="14" />## {{ t('courseGeneration.outlineReview.chapterHeading', '章标题') }}
              <span>·</span>
              <Heading3 :size="14" />### {{ t('courseGeneration.outlineReview.sectionHeading', '小节标题') }}
            </p>
          </div>

          <article v-if="blueprintNodes.length" ref="chaptersRef" class="formal-outline" data-testid="formal-outline-document">
            <header class="formal-outline__masthead">
              <div class="formal-outline__kicker">
                <FileText :size="15" />
                <span>{{ t('courseGeneration.outlineReview.documentKicker', '正式教学大纲') }}</span>
              </div>
              <h1>{{ documentTitle }}</h1>
              <p>{{ documentPositioning || t('courseGeneration.outlineReview.positioningPending', '课程定位将在教学目标与章节结构中继续明确。') }}</p>
              <dl>
                <div><dt>{{ t('courseGeneration.outlineReview.documentChapters', '章节') }}</dt><dd>{{ documentChapters.length }}</dd></div>
                <div v-if="documentVisibleSectionCount"><dt>{{ t('courseGeneration.outlineReview.documentSections', '小节') }}</dt><dd>{{ documentVisibleSectionCount }}</dd></div>
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

            <section
              v-if="editorMode === 'visual'"
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
              @blur="syncRichEditorToNodes"
              @paste="handleRichEditorPaste"
              @keydown="handleEditorKeydown"
            />
            <section v-else class="outline-markdown-workspace" data-testid="outline-markdown-editor">
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
import DOMPurify from 'dompurify'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AlignCenter, AlignJustify, AlignLeft, AlignRight, ArrowRight, Bold, Braces, ChartNoAxesCombined, ChevronDown, ChevronUp, CircleCheck, Code2, FileText, FileType2, Heading2, Heading3, Highlighter, ImagePlus, IndentDecrease, IndentIncrease, Italic, Link2, List, ListOrdered, LoaderCircle, Minus, MoreHorizontal, Plus, Quote, Redo2, RemoveFormatting, Replace, Save, Search, Sigma, Sparkles, Strikethrough, Subscript, Superscript, Table2, TriangleAlert, Underline, Undo2 } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import MarkdownRenderer from './MarkdownRenderer.vue'
import type { Node, Task } from '../stores/types'
import { useCourseStore } from '../stores/course'
import { useCourseWorkspaceStore } from '../stores/courseWorkspace'
import { useGenerationStore } from '../stores/generation'
import { t } from '../shared/i18n'
import { renderMarkdown } from '../utils/markdown'
import { retrievalErrorTranslationKey } from '../utils/retrieval-errors'
import { createUuid } from '../utils/client-id'

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
const blueprintNodes = computed<any[]>(() => (
  Array.isArray(blueprintDraft.value?.nodes)
    ? blueprintDraft.value.nodes
    : Array.isArray(blueprintDraft.value?.course_blueprint?.nodes)
      ? blueprintDraft.value.course_blueprint.nodes
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
        title: chapterNode.node_name,
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
            section_number: `${chapterIndex + 1}.${sectionIndex + 1}`,
            title: node.node_name,
          }
        }),
      }
    })
  if (chapters.length || !blueprintNodes.value.length) return chapters
  return blueprintNodes.value.map((node, chapterIndex) => ({
    _node: node,
    node_id: node.node_id,
    chapter_number: chapterIndex + 1,
    title: node.node_name,
    learning_focus: node.learning_objective || '',
    learning_objective: node.learning_objective || '',
    sections: [],
  }))
})
const outlineEditorHtml = computed(() => documentChapters.value.map((chapter: any) => {
  const chapterNode = chapter._node || chapter
  const chapterId = escapeEditorAttribute(String(chapterNode.node_id || outlineNodeId('chapter')))
  const chapterTitle = editorFieldHtml(chapterNode, 'title_html', chapterNode.node_name || chapter.title)
  const chapterBody = editorBodyHtml(chapterNode, chapterNode.learning_objective || chapter.learning_focus)
  const chapterChange = proposalNodeAttributes(String(chapterNode.node_id || ''))
  const sections = (chapter.sections || []).map((section: any) => {
    const sectionNode = section._node || section
    const sectionId = escapeEditorAttribute(String(sectionNode.node_id || outlineNodeId('section')))
    const sectionTitle = editorFieldHtml(sectionNode, 'title_html', sectionNode.node_name || section.title)
    const sectionBody = editorBodyHtml(sectionNode, sectionNode.learning_objective)
    const sectionChange = proposalNodeAttributes(String(sectionNode.node_id || ''))
    const collapsed = chapter.sections.length === 1
      ? ' data-collapsed-single-section="true" aria-hidden="true"'
      : ''
    const singleBody = chapter.sections.length === 1
      ? ' data-single-section-body="true"'
      : ''
    return `<h3 data-node-id="${sectionId}"${sectionChange}${collapsed}>${sectionTitle}</h3><div data-node-body="${sectionId}"${sectionChange}${singleBody}>${sectionBody}</div>`
  }).join('')
  return `<h2 data-node-id="${chapterId}"${chapterChange}>${chapterTitle}</h2><div data-node-body="${chapterId}"${chapterChange}>${chapterBody}</div>${sections}`
}).join(''))
const documentVisibleSectionCount = computed(() => documentChapters.value.reduce(
  (total, chapter) => {
    const count = Array.isArray(chapter.sections) ? chapter.sections.length : 0
    return total + (count > 1 ? count : 0)
  },
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
  } else if (!syncMarkdownToNodes()) {
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

function handleRichEditorInput() {
  richEditorDirty.value = true
  refreshEditorStats()
  if (findPanelOpen.value && findQuery.value) refreshFindMatches(false)
  markManualChange(t('courseGeneration.outlineReview.manualChanged', '大纲已修改，保存后生效'))
}

function refreshEditorStats() {
  const value = editorMode.value === 'markdown'
    ? markdownDraft.value
    : String(richEditorRef.value?.textContent || editorPlainText(outlineEditorHtml.value))
  editorCharacterCount.value = value.replace(/\s/g, '').length
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
    activeNode.learning_objective = editorLearningObjective(bodyHtml, activeNode.learning_objective)
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
      const nodeName = String(element?.textContent || '').replace(/\s+/g, ' ').trim()
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
          title_html: sanitizeEditorHtml(element?.innerHTML || nodeName),
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
    actionError.value = t('courseGeneration.outlineReview.chapterRequired', '大纲至少需要保留一个章标题。')
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
  return editorMode.value === 'markdown' ? syncMarkdownToNodes() : syncRichEditorToNodes()
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
    qualityArtifact.value = clone(
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
  richEditorDirty.value = false
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
    richEditorDirty.value = false
    editorMode.value = 'visual'
    markdownDraft.value = ''
    qualityArtifact.value = clone(result?.quality_report || result?.draft?.course_outline_quality_report || {})
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

async function restoreHistoryVersion(historyEntryId: string) {
  if (!historyEntryId || acting.value || dirty.value) return false
  actionError.value = ''
  try {
    const result = await workspace.restoreBlueprintDraftVersion(props.courseId, historyEntryId)
    blueprintDraft.value = clone(result.draft || {})
    qualityArtifact.value = clone(result.quality_report || blueprintDraft.value.course_outline_quality_report || {})
    richEditorDirty.value = false
    editorMode.value = 'visual'
    markdownDraft.value = ''
    rememberedEditorRange = null
    syncNavigationFromDraft()
    baseline.value = draftSignature.value
    resetEditHistory()
    adjustmentProposal.value = null
    await nextTick()
    refreshEditorStats()
    ElMessage.success(t('courseGeneration.outlineReview.historyRestored', '已恢复大纲历史版本'))
    return true
  } catch (error: any) {
    actionError.value = error?.response?.data?.detail?.message
      || t('courseGeneration.outlineReview.historyRestoreFailed', '大纲历史版本恢复失败，请重试。')
    return false
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

defineExpose({
  finishEditing,
  confirmOutline,
  requestAiCandidate,
  resolveAiCandidate,
  focusAiCandidate,
  dirty,
  canUndo,
  canRedo,
  undoEdit,
  redoEdit,
  restoreHistoryVersion,
})
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
  border-top:1px solid #dfe3e9;
  color:#1d2639;
  font-size:21px;
  font-weight:820;
  line-height:1.4;
  letter-spacing:-.015em;
}
.outline-rich-editor :deep(h2:first-child) { border-top:0; }
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
.outline-rich-editor :deep([data-single-section-body="true"]) { margin-left:0; padding-bottom:22px; border-bottom:1px solid #e6e9ef; }
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
.outline-review[data-variant="inline"] .formal-outline__brief { padding-inline:64px; }
.outline-review[data-variant="inline"] .outline-quality,
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
