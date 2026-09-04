<template>
  <aside class="reference-tray" :class="{ 'is-compact': compact, 'is-question-bank': variant === 'question-bank', 'is-ppt': stage === 'ppt' }" :data-workflow-state="effectiveWorkflowState" :aria-label="trayTitle">
    <header v-if="stage === 'ppt' || variant !== 'default' || showClose" class="reference-tray__header" :class="{ 'is-close-only': variant === 'default' && stage !== 'ppt' }">
      <div v-if="stage === 'ppt' || variant !== 'default'" class="reference-tray__title">
        <span v-if="stage === 'ppt'"><Sparkles :size="16" /></span>
        <div>
          <strong>{{ trayTitle }}</strong>
          <small v-if="stage === 'ppt'">{{ t('courseWorkbench.references.pptSmartCount', '已加入 {count} 份').replace('{count}', String(selected.length)) }}</small>
          <small v-else-if="variant === 'question-bank'">
            {{ t('courseWorkbench.references.questionSourcesCount', '{count} 份').replace('{count}', String(questionSources.length)) }}
          </small>
        </div>
      </div>
      <button v-if="showClose" type="button" :title="t('common.close', '关闭')" :aria-label="t('common.close', '关闭')" @click="emit('close')"><X :size="16" /></button>
    </header>

    <button v-if="variant === 'default'" type="button" class="system-context" @click="emit('open-course-information')">
      <span><Database :size="16" /></span>
      <div>
        <strong>{{ t('courseWorkbench.courseInformation', '课程信息') }}</strong>
        <small>{{ t('courseWorkbench.references.systemContextHelp', '课时、课型与教学设置') }}</small>
      </div>
      <ChevronRight :size="15" />
    </button>

    <section
      v-if="variant === 'default' && lessonTargets.length && selected.length && (!completedWorkflow || completedSourceEditing)"
      class="reference-scope"
      :class="{ 'is-locked': workflowLocked }"
      data-testid="reference-scope"
    >
      <header>
        <div>
          <strong>{{ t('courseWorkbench.references.scopeTitle', '资料使用范围') }}</strong>
        </div>
        <span v-if="workflowLocked"><LockKeyhole :size="13" />{{ t('courseWorkbench.references.scopeLocked', '本轮已锁定') }}</span>
      </header>
      <ul class="reference-scope__list">
        <li v-for="item in selected" :key="item.asset_id" :data-asset-id="item.asset_id">
          <div class="reference-scope__file">
            <strong :title="item.source_label || item.filename">{{ item.source_label || item.filename }}</strong>
            <small>{{ appliedScopeSummary(item) }}</small>
          </div>
          <template v-if="!workflowLocked">
            <label>
              <span class="visually-hidden">{{ item.source_label || item.filename }}·{{ t('courseWorkbench.references.scopeTitle', '资料使用范围') }}</span>
              <select
                :value="scopeDraftFor(item).mode"
                :disabled="loading || saving || scopeApplyingAssetId === item.asset_id"
                @change="updateScopeMode(item.asset_id, $event)"
              >
                <option value="current">{{ t('courseWorkbench.references.scopeCurrent', '仅当前讲') }}</option>
                <option value="all">{{ t('courseWorkbench.references.scopeAll', '全部讲次') }}</option>
                <option value="range">{{ t('courseWorkbench.references.scopeRange', '连续范围') }}</option>
                <option value="custom">{{ t('courseWorkbench.references.scopeCustom', '指定多讲') }}</option>
              </select>
            </label>
            <div v-if="scopeDraftFor(item).mode === 'range'" class="reference-scope__range">
              <select
                :value="scopeDraftFor(item).rangeStartTargetId"
                :aria-label="`${item.source_label || item.filename}·${t('courseWorkbench.references.scopeRangeStart', '起始讲次')}`"
                @change="updateRangeTarget(item.asset_id, 'start', $event)"
              >
                <option v-for="target in lessonTargets" :key="target.id" :value="target.id">{{ target.label }}</option>
              </select>
              <span>—</span>
              <select
                :value="scopeDraftFor(item).rangeEndTargetId"
                :aria-label="`${item.source_label || item.filename}·${t('courseWorkbench.references.scopeRangeEnd', '结束讲次')}`"
                @change="updateRangeTarget(item.asset_id, 'end', $event)"
              >
                <option v-for="target in lessonTargets" :key="target.id" :value="target.id">{{ target.label }}</option>
              </select>
            </div>
            <div v-else-if="scopeDraftFor(item).mode === 'custom'" class="reference-scope__custom">
              <label v-for="target in lessonTargets" :key="target.id">
                <input
                  type="checkbox"
                  :value="target.id"
                  :checked="scopeDraftFor(item).customTargetIds.includes(target.id)"
                  @change="toggleCustomTarget(item.asset_id, target.id, $event)"
                />
                <span>{{ target.label }}</span>
              </label>
            </div>
            <button
              type="button"
              class="reference-scope__apply"
              :disabled="!scopeSelectionTargets(item).length || loading || saving || Boolean(scopeApplyingAssetId)"
              @click="applyReferenceScope(item)"
            >
              <LoaderCircle v-if="scopeApplyingAssetId === item.asset_id" :size="14" class="workflow-spinner" />
              <Check v-else :size="14" />
              {{ scopeApplyingAssetId === item.asset_id
                ? t('courseWorkbench.references.scopeApplying', '正在应用…')
                : t('courseWorkbench.references.scopeApply', '应用到所选讲次') }}
            </button>
          </template>
        </li>
      </ul>
    </section>

    <Transition name="tray-mode" mode="out-in">
      <section v-if="variant === 'default' && initialLoading" key="loading" class="source-status source-status--loading" aria-live="polite">
        <span><LoaderCircle :size="16" class="workflow-spinner" /></span>
        <div>
          <strong>{{ t('courseWorkbench.references.loadingTitle', '正在读取资料') }}</strong>
          <small>{{ t('courseWorkbench.references.loadingDetail', '即将恢复本阶段的资料与生成状态。') }}</small>
        </div>
      </section>

      <section v-else-if="variant === 'default' && workflowLocked && !hideWorkflowStatus" key="workflow" class="workflow-state" :class="`workflow-state--${effectiveWorkflowState}`" aria-live="polite">
        <header>
          <span class="workflow-state__signal">
            <LoaderCircle v-if="effectiveWorkflowState === 'generating'" :size="18" class="workflow-spinner" />
            <Pause v-else :size="17" />
          </span>
          <div><strong>{{ workflowStatusTitle }}</strong><small>{{ workflowStatusDetail }}</small></div>
        </header>
        <div class="workflow-progress" role="progressbar" :aria-valuenow="normalizedWorkflowProgress" aria-valuemin="0" aria-valuemax="100">
          <i :style="{ transform: `scaleX(${normalizedWorkflowProgress / 100})` }" />
        </div>
        <ul v-if="selected.length" class="workflow-source-list">
          <li v-for="item in selected" :key="item.asset_id">
            <span class="workflow-source-pulse"><Globe2 v-if="item.origin === 'web_search'" :size="15" /><FileText v-else :size="15" /></span>
            <div><strong>{{ item.source_label || item.filename }}</strong><small>{{ sourceRoleLabel(item) }}<template v-if="sourceProcessingLabel(item)"> · {{ sourceProcessingLabel(item) }}</template></small></div>
            <em>{{ effectiveWorkflowState === 'paused' ? t('courseWorkbench.references.pausedSource', '已保留') : t('courseWorkbench.references.usingSource', '使用中') }}</em>
          </li>
        </ul>
        <p v-else class="workflow-no-sources">{{ t('courseWorkbench.references.generatingWithoutSources', '未添加补充资料，系统正在使用课程信息与已确认内容。') }}</p>
        <footer>
          <button v-if="effectiveWorkflowState === 'generating' && workflowCanPause" type="button" @click="emit('pause-workflow')"><Pause :size="14" />{{ t('courseWorkbench.pause', '暂停') }}</button>
          <button v-if="effectiveWorkflowState === 'paused' && workflowCanResume" class="workflow-resume" type="button" @click="emit('resume-workflow')"><Play :size="14" />{{ t('courseWorkbench.continue', '继续') }}</button>
          <button v-if="workflowCanCancel" type="button" @click="emit('cancel-workflow')"><X :size="14" />{{ t('common.cancel', '取消') }}</button>
        </footer>
      </section>

      <section v-else-if="variant === 'default' && workflowLocked" key="workflow-sources" class="workflow-sources">
        <div class="group-heading">
          <strong>{{ t('courseWorkbench.references.currentSources', '本次使用') }}</strong>
          <small>{{ selected.length }}</small>
        </div>
        <ul v-if="selected.length" class="workflow-source-list workflow-source-list--quiet">
          <li v-for="item in selected" :key="item.asset_id">
            <span class="workflow-source-pulse"><Globe2 v-if="item.origin === 'web_search'" :size="15" /><FileText v-else :size="15" /></span>
            <div><strong>{{ item.source_label || item.filename }}</strong><small>{{ sourceRoleLabel(item) }}</small></div>
          </li>
        </ul>
        <p v-else class="workflow-no-sources">{{ t('courseWorkbench.references.noAdditionalSources', '未使用补充资料') }}</p>
      </section>

      <div v-else-if="variant === 'default'" key="sources" class="reference-interactive">
        <section v-if="effectiveWorkflowState !== 'collecting' && (!completedWorkflow || completedSourceEditing) && (!hideWorkflowStatus || sourceSelectionDirty || completedSourceEditing || sourceReadiness.kind !== 'ready')" class="source-status" :class="[`source-status--${effectiveWorkflowState}`, `source-status--sources-${sourceReadiness.kind}`, { 'is-editing': completedSourceEditing, 'is-dirty': sourceSelectionDirty }]" aria-live="polite">
          <span><LoaderCircle v-if="sourceReadiness.kind === 'processing'" :size="16" class="workflow-spinner" /><TriangleAlert v-else-if="effectiveWorkflowState === 'failed' || sourceSelectionDirty || sourceReadiness.kind === 'failed'" :size="16" /><CheckCircle2 v-else-if="completedWorkflow" :size="16" /><Upload v-else :size="16" /></span>
          <div><strong>{{ displayedWorkflowStatusTitle }}</strong><small>{{ displayedWorkflowStatusDetail }}</small></div>
          <div v-if="(effectiveWorkflowState === 'failed' && workflowCanRetry) || sourceSelectionDirty || completedSourceEditing" class="source-status__actions">
            <button v-if="effectiveWorkflowState === 'failed' && workflowCanRetry" type="button" class="source-status__retry" :disabled="sourceGenerationBlocked" @click="emit('retry-workflow')">
              <RotateCcw :size="13" />{{ t('courseWorkbench.references.retryGeneration', '重试生成') }}
            </button>
            <button v-if="sourceSelectionDirty" type="button" class="source-status__regenerate" :disabled="sourceGenerationBlocked" :title="sourceGenerationBlocked ? sourceBlockReason : undefined" @click="emit('regenerate-workflow')">
              <RotateCcw :size="13" />{{ stage === 'ppt'
                ? t('courseWorkbench.references.openPptToRegenerate', '前往 PPT 工作台重新生成')
                : t('courseWorkbench.references.regenerateWithAdjustedSources', '使用新资料重新生成') }}
            </button>
            <button v-if="completedSourceEditing" type="button" class="source-status__collapse" @click="sourceEditing = false">
              <ChevronUp :size="13" />{{ t('courseWorkbench.references.finishAdjusting', '收起调整') }}
            </button>
          </div>
        </section>

        <section v-if="completedSnapshotVisible" class="current-source-summary" aria-live="polite">
          <div class="group-heading">
            <strong>{{ completedSourceStatusTitle }}</strong>
            <small v-if="displayedSourceSnapshot.length">{{ displayedSourceSnapshot.length }}</small>
          </div>
          <ul v-if="displayedSourceSnapshot.length" class="current-source-list">
            <li v-for="item in displayedSourceSnapshot" :key="item.asset_id">
              <span><Globe2 v-if="item.origin === 'web_search'" :size="16" /><FileText v-else :size="16" /></span>
              <div><strong>{{ item.source_label || item.filename }}</strong><small>{{ sourceRoleLabel(item) }}<template v-if="sourceProcessingLabel(item)"> · {{ sourceProcessingLabel(item) }}</template></small></div>
              <Check :size="15" />
            </li>
          </ul>
          <div class="current-source-actions">
            <button v-if="sourceSelectionDirty" type="button" class="source-status__regenerate" :disabled="sourceGenerationBlocked" :title="sourceGenerationBlocked ? sourceBlockReason : undefined" @click="emit('regenerate-workflow')">
              <RotateCcw :size="13" />{{ stage === 'ppt'
                ? t('courseWorkbench.references.openPptToRegenerate', '前往 PPT 工作台重新生成')
                : t('courseWorkbench.references.regenerateWithAdjustedSources', '使用新资料重新生成') }}
            </button>
            <button type="button" class="current-source-adjust" :disabled="sourceOperationBusy" @click="beginSourceEditing">
              <SlidersHorizontal :size="15" />{{ sourceSelectionDirty ? t('courseWorkbench.references.continueAdjustingSources', '继续调整资料') : t('courseWorkbench.references.adjustSources', '调整资料') }}
            </button>
          </div>
          <small v-if="sourceSelectionDirty" class="current-source-hint">{{ t('courseWorkbench.references.pendingAdjustedSourcesHint', '以上仍是当前内容实际使用的资料；本次调整将在重新生成后生效。') }}</small>
        </section>

        <template v-else>
          <button
            v-if="previousAvailableSources.length"
            type="button"
            class="reuse-previous"
            :disabled="loading || saving"
            @click="reusePreviousSources"
          >
            <CopyPlus :size="15" />
            <span>{{ t('courseWorkbench.references.reusePrevious', '沿用上一讲资料') }}</span>
            <small>{{ previousAvailableSources.length }}</small>
          </button>

        <section v-if="stage === 'ppt'" class="source-group ppt-smart-sources">
          <div class="group-heading"><strong>{{ t('courseWorkbench.references.pptCurrentSources', '本次使用') }}</strong><small>{{ loading || saving ? t('courseWorkbench.references.processing', '处理中…') : selected.length }}</small></div>
          <div v-if="selected.length" class="ppt-smart-source-list">
            <div v-for="item in selected" :key="item.asset_id" class="ppt-smart-source-item">
              <span><Globe2 v-if="item.origin === 'web_search'" :size="17" /><FileText v-else :size="17" /></span>
              <div>
                <strong>{{ item.source_label || item.filename }}</strong>
                <small>{{ sourceRoleLabel(item) }}<template v-if="item.origin !== 'web_search'"> · {{ fileSize(item.size_bytes) }}</template></small>
              </div>
              <button type="button" :aria-label="t('common.remove', '移除')" :disabled="loading || saving" @click="removeSource(item.asset_id)"><X :size="14" /></button>
            </div>
          </div>
          <div v-else class="ppt-smart-empty">
            <Sparkles :size="20" />
            <strong>{{ t('courseWorkbench.references.pptEmpty', '尚未添加补充资料') }}</strong>
            <span>{{ t('courseWorkbench.references.pptEmptyHint', 'AI 将先使用当前可用讲义，新增资料会显示在这里。') }}</span>
          </div>
          <div class="ppt-smart-actions">
            <button type="button" :disabled="loading || saving" :class="{ dragging: dragRole === 'reference' }" @click="smartInput?.click()" @dragover.prevent="dragRole = 'reference'" @dragleave="dragRole = ''" @drop.prevent="handleSmartDrop"><Plus :size="16" />{{ t('courseWorkbench.references.pptAddSources', '添加资料') }}</button>
            <button v-if="webResearchAvailable" type="button" :disabled="loading || saving" @click="researchVisible = true"><Search :size="16" />{{ t('courseWorkbench.references.pptWebResearch', '联网查找') }}</button>
          </div>
          <input ref="smartInput" class="visually-hidden" type="file" multiple @change="handleSmartInput" />
        </section>

        <template v-else>
          <section class="source-group source-group--primary">
            <div class="group-heading"><strong>{{ t('courseWorkbench.references.primary', '资料文件') }}</strong><small>{{ t('courseWorkbench.references.primaryLimit', '最多 1 份') }}</small></div>
            <div class="drop-zone" :class="{ 'has-file': primarySource, dragging: dragRole === 'primary' }" @dragover.prevent="dragRole = 'primary'" @dragleave="dragRole = ''" @drop.prevent="handleDrop($event, 'primary')">
              <template v-if="primarySource">
                <FileText :size="19" />
                <div><strong>{{ primarySource.filename }}</strong><small>{{ fileSize(primarySource.size_bytes) }}<template v-if="sourceProcessingLabel(primarySource)"> · {{ sourceProcessingLabel(primarySource) }}</template></small></div>
                <button type="button" :disabled="loading || saving" :aria-label="t('common.remove', '移除')" @click="removeSource(primarySource.asset_id)"><X :size="15" /></button>
              </template>
              <button v-else type="button" class="empty-drop" :disabled="loading || saving" @click="primaryInput?.click()"><Plus :size="18" /><span>{{ t('courseWorkbench.references.addPrimary', '上传资料文件') }}</span></button>
            </div>
            <input ref="primaryInput" class="visually-hidden" type="file" @change="handleInput($event, 'primary')" />
          </section>

          <section class="source-group source-group--references">
            <div class="group-heading"><strong>{{ t('courseWorkbench.references.supporting', '参考文件') }}</strong><small>{{ referenceSources.length }}</small></div>
            <div class="reference-list">
              <div v-for="item in referenceSources" :key="item.asset_id" class="reference-item">
                <FileText :size="17" /><div><strong>{{ item.filename }}</strong><small>{{ fileSize(item.size_bytes) }}<template v-if="sourceProcessingLabel(item)"> · {{ sourceProcessingLabel(item) }}</template></small></div><button type="button" :disabled="loading || saving" :aria-label="t('common.remove', '移除')" @click="removeSource(item.asset_id)"><X :size="14" /></button>
              </div>
              <button type="button" class="reference-add" :disabled="loading || saving" :class="{ dragging: dragRole === 'reference' }" @click="referenceInput?.click()" @dragover.prevent="dragRole = 'reference'" @dragleave="dragRole = ''" @drop.prevent="handleDrop($event, 'reference')"><Plus :size="16" />{{ t('courseWorkbench.references.addSupporting', '上传参考文件') }}</button>
            </div>
            <input ref="referenceInput" class="visually-hidden" type="file" multiple @change="handleInput($event, 'reference')" />
          </section>
        </template>

          <section v-if="webResearchAvailable || webSources.length" class="source-group source-group--web">
          <div class="group-heading"><strong>{{ t('courseWorkbench.references.webSources', '联网来源') }}</strong><small>{{ webSources.length }}</small></div>
          <div class="web-source-list">
            <div v-for="item in webSources" :key="item.asset_id" class="web-source-item">
              <Globe2 :size="17" />
              <div><strong>{{ item.source_label || item.filename }}</strong><a v-if="item.source_metadata?.url" :href="String(item.source_metadata.url)" target="_blank" rel="noopener noreferrer">{{ item.source_metadata.domain || item.source_metadata.url }}<ExternalLink :size="11" /></a><small v-else>{{ item.filename }}</small></div>
              <button type="button" :disabled="loading || saving" :aria-label="t('common.remove', '移除')" @click="removeSource(item.asset_id)"><X :size="14" /></button>
            </div>
            <button v-if="webResearchAvailable" type="button" class="web-research-open" :disabled="loading || saving" @click="researchVisible = true"><Search :size="16" />{{ webSources.length ? t('courseWorkbench.references.continueWebResearch', '继续检索') : t('courseWorkbench.references.startWebResearch', '添加联网来源') }}</button>
          </div>
          </section>

          <section v-if="materials.length" class="material-library">
            <div class="group-heading"><strong>{{ t('courseWorkbench.references.courseMaterials', '课程资料库') }}</strong><small>{{ materials.length }}</small></div>
            <button v-for="item in availableMaterials" :key="item.asset_id" type="button" :disabled="loading || saving" @click="addExisting(item)"><FileText :size="16" /><span>{{ item.filename }}</span><Plus :size="14" /></button>
            <p v-if="!availableMaterials.length">{{ t('courseWorkbench.references.allSelected', '当前资料已全部引用') }}</p>
          </section>
        </template>

        <div v-if="$slots['workflow-action']" class="reference-workflow-action">
          <slot name="workflow-action" />
        </div>
      </div>
    </Transition>

    <section v-if="variant === 'question-bank'" class="source-group source-group--question-bank">
      <div class="reference-list">
        <div v-for="item in questionSources" :key="item.asset_id" class="reference-item">
          <FileText :size="17" /><div><strong>{{ item.filename }}</strong><small>{{ fileSize(item.size_bytes) }}</small></div><button type="button" :aria-label="t('common.remove', '移除')" @click="removeSource(item.asset_id)"><X :size="14" /></button>
        </div>
        <button
          type="button"
          class="reference-add"
          :class="{ dragging: dragRole === 'question_source' }"
          @click="questionSourceInput?.click()"
          @dragover.prevent="dragRole = 'question_source'"
          @dragleave="dragRole = ''"
          @drop.prevent="handleDrop($event, 'question_source')"
        ><Plus :size="16" />{{ t('courseWorkbench.references.addQuestionSourcesCompact', '添加真题') }}</button>
      </div>
      <input ref="questionSourceInput" class="visually-hidden" type="file" multiple @change="handleInput($event, 'question_source')" />
    </section>

    <p v-if="error" class="tray-error" role="alert">{{ error }}</p>
    <WebResearchDialog v-if="variant === 'default' && webResearchAvailable" :visible="researchVisible" :course-id="courseId" :stage="stage" :lesson-id="lessonId" @close="researchVisible = false" @saved="handleWebSaved" />
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Check, CheckCircle2, ChevronRight, ChevronUp, CopyPlus, Database, ExternalLink, FileText, Globe2, LoaderCircle, LockKeyhole, Pause, Play, Plus, RotateCcw, Search, SlidersHorizontal, Sparkles, TriangleAlert, Upload, X } from 'lucide-vue-next'
import WebResearchDialog from './WebResearchDialog.vue'
import { t } from '../shared/i18n'
import http, { teacherReadRequestConfig, teacherRequestConfig } from '../utils/http'

export type CourseReferenceItem = {
  package_id: string
  asset_id: string
  material_asset_id: string
  filename: string
  relative_path: string
  size_bytes: number
  uploaded_at?: string
  role: 'primary' | 'reference' | 'question_source'
  origin?: 'material' | 'web_search'
  source_label?: string
  reuse_policy?: 'verbatim_allowed' | 'reference_only' | 'original_generation'
  rights_basis?: 'teacher_asserted' | 'open_license' | 'license_unknown' | 'platform_owned'
  source_metadata?: Record<string, any>
  category?: string
  document_type?: 'outline' | 'lesson_plan' | 'script' | 'ppt' | 'question_bank' | 'school_material' | 'other'
  processing_status?: 'pending' | 'processing' | 'ready' | 'failed' | string
  parse_status?: 'pending' | 'processing' | 'ready' | 'failed' | string
  parse_error?: string
  parse_warnings?: string[]
  usages?: Array<{
    target_id?: string
    target_type?: string
    target_label?: string
    role?: 'primary' | 'reference' | 'question_source'
  }>
}

export type CourseReferenceLessonTarget = {
  id: string
  lessonId: string
  label: string
  position: number
}

type ReferenceScopeMode = 'current' | 'all' | 'range' | 'custom'

type ReferenceScopeDraft = {
  mode: ReferenceScopeMode
  rangeStartTargetId: string
  rangeEndTargetId: string
  customTargetIds: string[]
  appliedTargetIds: string[]
}

export type CourseReferenceWorkflowState = 'auto' | 'collecting' | 'ready' | 'generating' | 'paused' | 'completed' | 'failed'
export type CourseReferenceSourceState = { busy: boolean; blocked: boolean; reason: string }

type GenerationSourceSnapshot = {
  snapshot_id?: string
  package_id?: string
  target_id: string
  target_type?: string
  target_label?: string
  task_id?: string
  captured_at?: string
  sources: Array<{
    source_asset_id: string
    material_asset_id?: string
    source_label?: string
    role?: 'primary' | 'reference' | 'question_source'
  }>
}

const props = withDefaults(defineProps<{
  courseId: string
  modelValue: CourseReferenceItem[]
  stage?: string
  lessonId?: string
  scopeTargetId?: string
  scopeTargetType?: string
  scopeTargetLabel?: string
  scopeTargetPosition?: number
  refreshToken?: number
  previousScopeTargetId?: string
  lessonTargets?: CourseReferenceLessonTarget[]
  showClose?: boolean
  compact?: boolean
  variant?: 'default' | 'question-bank'
  hideWorkflowStatus?: boolean
  workflowState?: CourseReferenceWorkflowState
  workflowLabel?: string
  workflowDetail?: string
  workflowProgress?: number
  workflowCanPause?: boolean
  workflowCanResume?: boolean
  workflowCanCancel?: boolean
  workflowCanRetry?: boolean
}>(), {
  stage: 'foundation',
  lessonId: '',
  scopeTargetId: '',
  scopeTargetType: '',
  scopeTargetLabel: '',
  scopeTargetPosition: 0,
  refreshToken: 0,
  previousScopeTargetId: '',
  lessonTargets: () => [],
  showClose: false,
  compact: false,
  variant: 'default',
  hideWorkflowStatus: false,
  workflowState: 'auto',
  workflowLabel: '',
  workflowDetail: '',
  workflowProgress: 0,
  workflowCanPause: false,
  workflowCanResume: false,
  workflowCanCancel: false,
  workflowCanRetry: false,
})
const emit = defineEmits<{
  (event: 'update:modelValue', value: CourseReferenceItem[]): void
  (event: 'open-course-information'): void
  (event: 'pause-workflow'): void
  (event: 'resume-workflow'): void
  (event: 'cancel-workflow'): void
  (event: 'retry-workflow'): void
  (event: 'regenerate-workflow'): void
  (event: 'source-state-change', value: CourseReferenceSourceState): void
  (event: 'close'): void
}>()
const materials = ref<CourseReferenceItem[]>([])
const selected = ref<CourseReferenceItem[]>([])
const storedWebReferences = ref<CourseReferenceItem[]>([])
const configuredTargetIds = ref(new Set<string>())
const generationSourceSnapshots = ref<Record<string, GenerationSourceSnapshot>>({})
const localGenerationSourceBaselines = ref<Record<string, GenerationSourceSnapshot>>({})
const loading = ref(false)
const saving = ref(false)
const hasLoaded = ref(false)
const error = ref('')
const researchVisible = ref(false)
const sourceEditing = ref(false)
const webResearchAvailable = ref(true)
const dragRole = ref<'' | 'primary' | 'reference' | 'question_source'>('')
const questionSourceInput = ref<HTMLInputElement | null>(null)
const primaryInput = ref<HTMLInputElement | null>(null)
const referenceInput = ref<HTMLInputElement | null>(null)
const smartInput = ref<HTMLInputElement | null>(null)
const scopeDrafts = ref<Record<string, ReferenceScopeDraft>>({})
const scopeApplyingAssetId = ref('')
const primarySource = computed(() => selected.value.find(item => item.role === 'primary'))
const referenceSources = computed(() => selected.value.filter(item => item.role === 'reference' && item.origin !== 'web_search'))
const questionSources = computed(() => selected.value.filter(item => item.role === 'question_source'))
const webSources = computed(() => selected.value.filter(item => item.role === 'reference' && item.origin === 'web_search'))
const availableMaterials = computed(() => {
  const chosen = new Set(selected.value.map(item => item.asset_id))
  return materials.value.filter(item => !chosen.has(item.asset_id))
})
function orderedLessonTargets() {
  return [...props.lessonTargets].sort((left, right) => left.position - right.position)
}
function itemAppliedTargetIds(item: CourseReferenceItem) {
  const allowed = new Set(props.lessonTargets.map(target => target.id))
  const stored = (item.usages || [])
    .filter(usage => (!props.scopeTargetType || usage.target_type === props.scopeTargetType) && allowed.has(String(usage.target_id || '')))
    .map(usage => String(usage.target_id))
  if (stored.length) return [...new Set(stored)]
  return props.scopeTargetId ? [props.scopeTargetId] : []
}
function createScopeDraft(item: CourseReferenceItem): ReferenceScopeDraft {
  const targets = orderedLessonTargets()
  const appliedTargetIds = itemAppliedTargetIds(item)
  const selectedTargets = targets.filter(target => appliedTargetIds.includes(target.id))
  const isAll = targets.length > 0 && selectedTargets.length === targets.length
  const isContinuous = selectedTargets.length > 1 && selectedTargets.every((target, index) => (
    index === 0 || target.position === selectedTargets[index - 1]!.position + 1
  ))
  const mode: ReferenceScopeMode = isAll
    ? 'all'
    : selectedTargets.length === 1 && selectedTargets[0]!.id === props.scopeTargetId
      ? 'current'
      : isContinuous
        ? 'range'
        : 'custom'
  return {
    mode,
    rangeStartTargetId: selectedTargets[0]?.id || props.scopeTargetId || targets[0]?.id || '',
    rangeEndTargetId: selectedTargets.at(-1)?.id || props.scopeTargetId || targets.at(-1)?.id || '',
    customTargetIds: [...appliedTargetIds],
    appliedTargetIds: [...appliedTargetIds],
  }
}
function scopeDraftFor(item: CourseReferenceItem) {
  return scopeDrafts.value[item.asset_id] || createScopeDraft(item)
}
function ensureScopeDrafts() {
  const next = { ...scopeDrafts.value }
  for (const item of selected.value) {
    if (!next[item.asset_id]) next[item.asset_id] = createScopeDraft(item)
  }
  scopeDrafts.value = next
}
function scopeSelectionTargets(item: CourseReferenceItem) {
  const draft = scopeDraftFor(item)
  const targets = [...props.lessonTargets].sort((left, right) => left.position - right.position)
  if (!targets.length) return []
  if (draft.mode === 'all') return targets
  if (draft.mode === 'range') {
    const start = targets.findIndex(target => target.id === draft.rangeStartTargetId)
    const end = targets.findIndex(target => target.id === draft.rangeEndTargetId)
    if (start < 0 || end < 0) return []
    return targets.slice(Math.min(start, end), Math.max(start, end) + 1)
  }
  if (draft.mode === 'custom') {
    const chosen = new Set(draft.customTargetIds)
    return targets.filter(target => chosen.has(target.id))
  }
  return targets.filter(target => target.id === props.scopeTargetId)
}
function appliedScopeSummary(item: CourseReferenceItem) {
  const appliedTargetIds = scopeDraftFor(item).appliedTargetIds
  const targets = props.lessonTargets.filter(target => appliedTargetIds.includes(target.id))
    .sort((left, right) => left.position - right.position)
  if (!targets.length) return props.scopeTargetLabel || t('courseWorkbench.references.scopeCurrent', '仅当前讲')
  if (targets.length === props.lessonTargets.length) return t('courseWorkbench.references.scopeAllCount', '全部 {count} 讲').replace('{count}', String(targets.length))
  if (targets.length === 1) return targets[0]!.label
  const continuous = targets.every((target, index) => index === 0 || target.position === targets[index - 1]!.position + 1)
  return continuous
    ? t('courseWorkbench.references.scopeRangeSummary', '{start} 至 {end}').replace('{start}', targets[0]!.label).replace('{end}', targets.at(-1)!.label)
    : t('courseWorkbench.references.scopeCustomSummary', '指定 {count} 讲').replace('{count}', String(targets.length))
}
const trayTitle = computed(() => {
  if (props.variant === 'question-bank') {
    return t('courseWorkbench.references.questionSources', '真题资料')
  }
  return props.stage === 'ppt'
    ? t('courseWorkbench.references.pptSmartTitle', 'PPT 智能资料')
    : t('courseWorkbench.references.title', '信息来源')
})
const effectiveWorkflowState = computed<Exclude<CourseReferenceWorkflowState, 'auto'>>(() => (
  props.workflowState === 'auto'
    ? selected.value.length ? 'ready' : 'collecting'
    : props.workflowState
))
const workflowLocked = computed(() => ['generating', 'paused'].includes(effectiveWorkflowState.value))
const completedWorkflow = computed(() => effectiveWorkflowState.value === 'completed')
const completedSourceEditing = computed(() => completedWorkflow.value && sourceEditing.value)
const completedSnapshotVisible = computed(() => completedWorkflow.value && !sourceEditing.value && hasLoaded.value)
const serverGenerationSourceSnapshot = computed(() => (
  props.scopeTargetId ? generationSourceSnapshots.value[props.scopeTargetId] || null : null
))
const activeGenerationSourceSnapshot = computed(() => (
  serverGenerationSourceSnapshot.value
  || (props.scopeTargetId ? localGenerationSourceBaselines.value[props.scopeTargetId] || null : null)
))
function sourceSignature(value: Array<{ source_asset_id?: string; asset_id?: string; role?: string }>) {
  return value
    .map(item => `${item.source_asset_id || item.asset_id || ''}:${item.role || 'reference'}`)
    .sort()
    .join('|')
}
const snapshotSourceItems = computed<CourseReferenceItem[]>(() => {
  const snapshot = activeGenerationSourceSnapshot.value
  if (!snapshot) return []
  const known = new Map([...materials.value, ...selected.value].map(item => [item.asset_id, item]))
  const webByMaterialId = new Map(storedWebReferences.value.map(item => [item.material_asset_id, item]))
  return (snapshot.sources || []).map(source => {
    const item = known.get(source.source_asset_id)
    const web = webByMaterialId.get(String(source.material_asset_id || item?.material_asset_id || ''))
    return {
      ...item,
      ...web,
      package_id: snapshot.package_id || item?.package_id || '',
      asset_id: source.source_asset_id,
      material_asset_id: String(source.material_asset_id || item?.material_asset_id || ''),
      filename: source.source_label || item?.filename || t('courseWorkbench.references.unavailableSource', '历史资料'),
      relative_path: item?.relative_path || '',
      size_bytes: Number(item?.size_bytes || 0),
      uploaded_at: item?.uploaded_at,
      role: source.role === 'primary' ? 'primary' : source.role === 'question_source' ? 'question_source' : 'reference',
    }
  })
})
const sourceSelectionDirty = computed(() => Boolean(
  completedWorkflow.value
  && activeGenerationSourceSnapshot.value
  && sourceSignature(selected.value) !== sourceSignature(activeGenerationSourceSnapshot.value.sources),
))
const displayedSourceSnapshot = computed(() => activeGenerationSourceSnapshot.value
  ? snapshotSourceItems.value
  : selected.value)
function sourceStateValue(item: CourseReferenceItem) {
  return String(
    item.processing_status
    || item.parse_status
    || item.source_metadata?.processing_status
    || item.source_metadata?.parse_status
    || '',
  ).toLowerCase()
}
const sourceReadiness = computed(() => {
  const failed = selected.value.find(item => ['failed', 'error', 'metadata_only'].includes(sourceStateValue(item)))
  if (failed) return {
    kind: 'failed' as const,
    reason: failed.parse_error || t('courseWorkbench.references.parseBlocked', '有资料未能读取，请移除或重新上传。'),
  }
  const processing = selected.value.find(item => ['uploaded', 'pending', 'parsing', 'processing'].includes(sourceStateValue(item)))
  if (processing) return {
    kind: 'processing' as const,
    reason: t('courseWorkbench.references.parseBlocking', '资料正在解析，完成后即可生成。'),
  }
  return { kind: 'ready' as const, reason: '' }
})
const sourceOperationBusy = computed(() => loading.value || saving.value || Boolean(scopeApplyingAssetId.value))
const sourceGenerationBlocked = computed(() => sourceOperationBusy.value || sourceReadiness.value.kind !== 'ready' || Boolean(error.value))
const sourceBlockReason = computed(() => {
  if (sourceOperationBusy.value) return t('courseWorkbench.references.sourcesUpdating', '正在更新资料…')
  return sourceReadiness.value.reason || error.value
})
const initialLoading = computed(() => !hasLoaded.value && loading.value)
const normalizedWorkflowProgress = computed(() => Math.max(0, Math.min(100, Number(props.workflowProgress || 0))))
const workflowStageLabel = computed(() => ({
  foundation: t('courseWorkbench.stages.foundation', '课程大纲'),
  lesson: t('courseWorkbench.stages.lesson', '本讲教案'),
  script: t('courseWorkbench.stages.script', '本讲讲义'),
  ppt: t('courseWorkbench.stages.ppt', '本讲 PPT'),
}[props.stage] || t('courseWorkbench.references.currentStage', '当前内容')))
const workflowStatusTitle = computed(() => props.workflowLabel || ({
  collecting: t('courseWorkbench.references.collectingTitle', '先准备本阶段资料'),
  ready: t('courseWorkbench.references.readyTitle', '资料已准备'),
  generating: t('courseWorkbench.references.generatingTitle', '{stage}正在使用这些资料').replace('{stage}', workflowStageLabel.value),
  paused: t('courseWorkbench.references.pausedTitle', '生成已暂停'),
  completed: t('courseWorkbench.references.completedTitle', '当前内容已完成'),
  failed: t('courseWorkbench.references.failedTitle', '生成已中断'),
}[effectiveWorkflowState.value]))
const workflowStatusDetail = computed(() => props.workflowDetail || ({
  collecting: t('courseWorkbench.references.collectingDetail', '上传一份资料文件，并按需补充参考文件。'),
  ready: t('courseWorkbench.references.readyDetail', '已选 {count} 份，开始生成后这里会显示使用状态。').replace('{count}', String(selected.value.length)),
  generating: t('courseWorkbench.references.generatingDetail', 'AI 正在读取资料并构建内容。'),
  paused: t('courseWorkbench.references.pausedDetail', '资料与进度已经保留，可继续或取消。'),
  completed: t('courseWorkbench.references.completedDetail', '当前内容使用了以下资料；调整后需要重新生成。'),
  failed: t('courseWorkbench.references.failedDetail', '资料仍然保留，可调整后重新生成。'),
}[effectiveWorkflowState.value]))
const displayedWorkflowStatusTitle = computed(() => sourceSelectionDirty.value
  ? sourceReadiness.value.kind === 'failed'
    ? t('courseWorkbench.references.adjustedSourcesFailedTitle', '资料调整未完成')
    : sourceReadiness.value.kind === 'processing'
      ? t('courseWorkbench.references.adjustedSourcesProcessingTitle', '资料正在处理')
      : t('courseWorkbench.references.adjustedSourcesPendingTitle', '资料已调整，当前内容待重新生成')
  : sourceReadiness.value.kind === 'failed'
    ? t('courseWorkbench.references.sourceFailedTitle', '有资料未能读取')
    : sourceReadiness.value.kind === 'processing'
      ? t('courseWorkbench.references.sourceProcessingTitle', '资料正在处理')
  : completedSourceEditing.value
    ? t('courseWorkbench.references.adjustingTitle', '正在调整资料')
    : workflowStatusTitle.value)
const displayedWorkflowStatusDetail = computed(() => sourceSelectionDirty.value
  ? sourceReadiness.value.kind === 'ready'
    ? t('courseWorkbench.references.adjustedSourcesPendingDetail', '当前内容仍使用上次生成时的资料；重新生成后才会应用本次调整。')
    : sourceReadiness.value.reason
  : sourceReadiness.value.kind !== 'ready'
    ? sourceReadiness.value.reason
  : completedSourceEditing.value
    ? t('courseWorkbench.references.adjustingDetail', '新增或移除资料不会直接改动已生成内容，重新生成后才会使用。')
    : workflowStatusDetail.value)
const completedSourceStatusTitle = computed(() => {
  if (sourceSelectionDirty.value) return displayedWorkflowStatusTitle.value
  return displayedSourceSnapshot.value.length
    ? t('courseWorkbench.references.currentSourcesTitle', '使用以下资料')
    : t('courseWorkbench.references.currentWithoutSources', '未使用资料')
})
const previousAvailableSources = computed(() => {
  if (!props.previousScopeTargetId) return []
  const chosen = new Set(selected.value.map(item => item.asset_id))
  return materials.value.flatMap(item => {
    if (chosen.has(item.asset_id)) return []
    const usage = item.usages?.find(link => link.target_id === props.previousScopeTargetId)
    if (!usage) return []
    return [{ ...item, role: usage.role === 'primary' ? 'primary' as const : 'reference' as const }]
  })
})

watch(() => props.modelValue, value => {
  selected.value = value.map(item => ({ ...item }))
  ensureScopeDrafts()
}, { immediate: true, deep: true })
watch([() => props.scopeTargetId, () => props.lessonTargets], () => {
  scopeDrafts.value = {}
  ensureScopeDrafts()
}, { immediate: true, deep: true })
function applySelection(value: CourseReferenceItem[], persist: boolean) {
  selected.value = value
  ensureScopeDrafts()
  emit('update:modelValue', value)
  if (persist && props.scopeTargetId && props.scopeTargetType) void persistScopedSelection(value)
}
function commit(value: CourseReferenceItem[]) {
  applySelection(value, true)
}
function beginSourceEditing() {
  if (
    completedWorkflow.value
    && props.scopeTargetId
    && !activeGenerationSourceSnapshot.value
  ) {
    localGenerationSourceBaselines.value = {
      ...localGenerationSourceBaselines.value,
      [props.scopeTargetId]: {
        target_id: props.scopeTargetId,
        target_type: props.scopeTargetType,
        target_label: props.scopeTargetLabel,
        sources: selected.value.map(item => ({
          source_asset_id: item.asset_id,
          material_asset_id: item.material_asset_id,
          source_label: item.source_label || item.filename,
          role: item.role,
        })),
      },
    }
  }
  sourceEditing.value = true
}
function fileSize(value: number) { return value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB` }
function sourceRoleLabel(item: CourseReferenceItem) {
  if (item.origin === 'web_search') return t('courseWorkbench.references.webSources', '联网来源')
  return item.role === 'primary'
    ? t('courseWorkbench.references.primaryMaterial', '原始材料')
    : t('courseWorkbench.references.referenceMaterial', '参考材料')
}
function sourceProcessingLabel(item: CourseReferenceItem) {
  const status = sourceStateValue(item)
  return {
    uploaded: t('courseWorkbench.references.parsePending', '等待解析'),
    pending: t('courseWorkbench.references.parsePending', '等待解析'),
    parsing: t('courseWorkbench.references.parsing', '解析中'),
    processing: t('courseWorkbench.references.parsing', '解析中'),
    parsed: t('courseWorkbench.references.parseReady', '已解析'),
    degraded: t('courseWorkbench.references.parseReady', '已解析'),
    ready: t('courseWorkbench.references.parseReady', '已解析'),
    completed: t('courseWorkbench.references.parseReady', '已解析'),
    metadata_only: t('courseWorkbench.references.parseFailed', '解析失败'),
    failed: t('courseWorkbench.references.parseFailed', '解析失败'),
    error: t('courseWorkbench.references.parseFailed', '解析失败'),
  }[status] || ''
}

async function resolvePackageId(value: CourseReferenceItem[]) {
  const direct = value[0]?.package_id || materials.value[0]?.package_id
  if (direct) return direct
  const response = await http.get('/api/teacher-course-spaces', teacherReadRequestConfig({ params: { course_id: props.courseId }, silentError: true }))
  return String(response.data?.[0]?.package_id || '')
}

type PersistedSource = {
  source_asset_id: string
  role: 'primary' | 'reference' | 'question_source'
}

function replaceLocalTargetSources(target: { id: string; label: string }, sources: PersistedSource[]) {
  const roles = new Map(sources.map(source => [source.source_asset_id, source.role]))
  const update = (item: CourseReferenceItem): CourseReferenceItem => {
    const usages = (item.usages || []).filter(usage => !(
      usage.target_id === target.id
      && (!props.scopeTargetType || usage.target_type === props.scopeTargetType)
    ))
    const role = roles.get(item.asset_id)
    if (role) usages.push({
      target_id: target.id,
      target_type: props.scopeTargetType,
      target_label: target.label,
      role,
    })
    return { ...item, usages }
  }
  materials.value = materials.value.map(update)
  selected.value = selected.value.map(update)
}

async function persistScopedSelection(value: CourseReferenceItem[], bindingMode: 'auto' | 'manual' = 'manual') {
  const fallbackTarget = props.scopeTargetId
    ? [{ id: props.scopeTargetId, label: props.scopeTargetLabel || props.scopeTargetId }]
    : []
  const targetId = props.scopeTargetId
  const targetType = props.scopeTargetType
  if (!fallbackTarget.length || !targetType) return
  saving.value = true
  error.value = ''
  try {
    const packageId = await resolvePackageId(value)
    if (!packageId) return
    const sources = value.map(item => ({ source_asset_id: item.asset_id, role: item.role }))
    await http.put(`/api/teacher-course-spaces/${packageId}/relationships`, {
      target_id: targetId,
      target_type: targetType,
      target_label: props.scopeTargetLabel || targetId,
      binding_mode: bindingMode,
      preserve_generation_snapshot_if_missing: completedWorkflow.value && !serverGenerationSourceSnapshot.value,
      sources,
    }, teacherRequestConfig({ silentError: true }))
    replaceLocalTargetSources(fallbackTarget[0]!, sources)
  } catch (reason: any) {
    const fallback = props.variant === 'question-bank'
      ? t('courseWorkbench.references.questionSourcesSaveFailed', '真题资料保存失败')
      : t('courseWorkbench.references.saveFailed', '本讲资料保存失败')
    if (targetId === props.scopeTargetId) error.value = String(reason?.response?.data?.detail || reason?.message || fallback)
  } finally {
    if (targetId === props.scopeTargetId) saving.value = false
  }
}

function updateScopeMode(assetId: string, event: Event) {
  const draft = scopeDrafts.value[assetId]
  if (!draft) return
  draft.mode = (event.target as HTMLSelectElement).value as ReferenceScopeMode
}

function updateRangeTarget(assetId: string, boundary: 'start' | 'end', event: Event) {
  const draft = scopeDrafts.value[assetId]
  if (!draft) return
  if (boundary === 'start') draft.rangeStartTargetId = (event.target as HTMLSelectElement).value
  else draft.rangeEndTargetId = (event.target as HTMLSelectElement).value
}

function toggleCustomTarget(assetId: string, targetId: string, event: Event) {
  const draft = scopeDrafts.value[assetId]
  if (!draft) return
  const checked = (event.target as HTMLInputElement).checked
  draft.customTargetIds = checked
    ? [...new Set([...draft.customTargetIds, targetId])]
    : draft.customTargetIds.filter(id => id !== targetId)
}

function knownSources() {
  const byId = new Map<string, CourseReferenceItem>()
  for (const source of [...materials.value, ...selected.value]) {
    const existing = byId.get(source.asset_id)
    byId.set(source.asset_id, {
      ...existing,
      ...source,
      usages: source.usages?.length ? source.usages : existing?.usages,
    })
  }
  return [...byId.values()]
}

function sourceRoleAtTarget(source: CourseReferenceItem, targetId: string) {
  return source.usages?.find(usage => (
    usage.target_id === targetId
    && (!props.scopeTargetType || usage.target_type === props.scopeTargetType)
  ))?.role
}

function sourcesForTarget(item: CourseReferenceItem, targetId: string, desiredTargetIds: Set<string>) {
  const sources = knownSources().flatMap(source => {
    if (source.asset_id === item.asset_id) {
      return desiredTargetIds.has(targetId) ? [{ source_asset_id: source.asset_id, role: item.role }] : []
    }
    const role = sourceRoleAtTarget(source, targetId)
    return role ? [{ source_asset_id: source.asset_id, role }] : []
  })
  if (item.role === 'primary' && desiredTargetIds.has(targetId)) {
    return sources.map(source => source.source_asset_id !== item.asset_id && source.role === 'primary'
      ? { ...source, role: 'reference' as const }
      : source)
  }
  return sources
}

async function applyReferenceScope(item: CourseReferenceItem) {
  const targets = scopeSelectionTargets(item)
  if (!targets.length || scopeApplyingAssetId.value || workflowLocked.value || !props.scopeTargetType) return
  const desiredTargetIds = new Set(targets.map(target => target.id))
  const affectedTargetIds = new Set([
    ...itemAppliedTargetIds(item),
    ...desiredTargetIds,
  ])
  const affectedTargets = orderedLessonTargets().filter(target => affectedTargetIds.has(target.id))
  scopeApplyingAssetId.value = item.asset_id
  error.value = ''
  try {
    const packageId = await resolvePackageId([item])
    if (!packageId) return
    for (const target of affectedTargets) {
      const sources = sourcesForTarget(item, target.id, desiredTargetIds)
      await http.put(`/api/teacher-course-spaces/${packageId}/relationships`, {
        target_id: target.id,
        target_type: props.scopeTargetType,
        target_label: target.label || target.id,
        binding_mode: 'manual',
        sources,
      }, teacherRequestConfig({ silentError: true }))
      replaceLocalTargetSources(target, sources)
    }
    const draft = scopeDrafts.value[item.asset_id]
    if (draft) draft.appliedTargetIds = [...desiredTargetIds]
  } catch (reason: any) {
    error.value = String(reason?.response?.data?.detail || reason?.message || t('courseWorkbench.references.saveFailed', '本讲资料保存失败'))
  } finally {
    scopeApplyingAssetId.value = ''
  }
}

async function loadMaterials() {
  try {
    const response = await http.get('/api/materials', teacherReadRequestConfig({ params: { course_id: props.courseId }, silentError: true }))
    const webByMaterialId = new Map([...storedWebReferences.value, ...webSources.value].map(item => [item.material_asset_id, item]))
    configuredTargetIds.value = new Set(response.data?.configured_source_target_ids || [])
    generationSourceSnapshots.value = response.data?.generation_source_snapshots || {}
    materials.value = (response.data?.assets || []).map((item: CourseReferenceItem) => ({ ...item, ...(webByMaterialId.get(item.material_asset_id) || {}), role: 'reference' }))
  } catch (reason: any) { error.value = String(reason?.response?.data?.detail || reason?.message || t('courseWorkbench.references.loadFailed', '课程资料读取失败')) }
}

function documentTypePreference() {
  if (props.variant === 'question-bank') return ['question_bank']
  if (props.stage === 'foundation') return ['outline', 'school_material']
  if (props.stage === 'lesson') return ['lesson_plan']
  if (props.stage === 'script') return ['script', 'lesson_plan']
  if (props.stage === 'ppt') return ['ppt', 'script', 'lesson_plan']
  return []
}

function lessonRelevance(item: CourseReferenceItem) {
  const text = `${item.relative_path} ${item.filename}`.toLowerCase()
  const position = Math.max(0, Number(props.scopeTargetPosition || 0))
  let score = 0
  if (position && new RegExp(`第\\s*0*${position}\\s*[讲章节课]`).test(text)) score += 60
  if (position && new RegExp(`(^|[^0-9])0*${position}([^0-9]|$)`).test(text)) score += 20
  const title = String(props.scopeTargetLabel || '').replace(/^第\s*[0-9一二三四五六七八九十百]+\s*[讲章节课]\s*/, '').trim().toLowerCase()
  if (title.length >= 2 && text.includes(title)) score += 45
  return score
}

function recommendedSources() {
  const preferences = documentTypePreference()
  if (!preferences.length) return []
  const candidates = materials.value
    .filter(item => item.material_asset_id && preferences.includes(String(item.document_type || '')))
    .map(item => ({
      item,
      typeRank: preferences.indexOf(String(item.document_type || '')),
      relevance: lessonRelevance(item),
    }))
    .sort((left, right) => (
      left.typeRank - right.typeRank
      || right.relevance - left.relevance
      || String(right.item.uploaded_at || '').localeCompare(String(left.item.uploaded_at || ''))
    ))
  if (!candidates.length) return []
  const primary = candidates[0]!
  const related = candidates.slice(1).filter(candidate => (
    props.stage === 'foundation'
    || candidate.relevance > 0 && candidate.relevance === primary.relevance
  )).slice(0, 4)
  const role = props.variant === 'question-bank' ? 'question_source' as const : 'primary' as const
  return [
    { ...primary.item, role },
    ...related.map(candidate => ({ ...candidate.item, role: props.variant === 'question-bank' ? 'question_source' as const : 'reference' as const })),
  ]
}

function mergeWebReferences(references: CourseReferenceItem[]) {
  const next = [...selected.value]
  for (const reference of references) {
    const normalized = { ...reference, role: 'reference' as const, origin: 'web_search' as const }
    const index = next.findIndex(item => item.asset_id === normalized.asset_id || item.material_asset_id === normalized.material_asset_id)
    if (index >= 0) next[index] = normalized; else next.push(normalized)
  }
  commit(next)
}

async function loadWebReferences() {
  try {
    const response = await http.get(`/api/courses/${props.courseId}/web-research`, teacherReadRequestConfig({ params: { stage: props.stage, lesson_id: props.lessonId }, silentError: true }))
    storedWebReferences.value = response.data?.accepted_references || []
  } catch (reason: any) { error.value = String(reason?.response?.data?.detail?.message || reason?.response?.data?.detail || reason?.message || t('courseWorkbench.webResearch.loadFailed', '调研记录读取失败')) }
}

async function loadWebResearchCapability() {
  try {
    const response = await http.get(
      `/api/courses/${props.courseId}/web-research/capability`,
      teacherReadRequestConfig({ silentError: true }),
    )
    webResearchAvailable.value = response.data?.available !== false
  } catch {
    webResearchAvailable.value = false
    researchVisible.value = false
  }
}

async function loadAll() {
  const targetId = props.scopeTargetId
  loading.value = true; error.value = ''
  try {
    if (props.variant === 'default') {
      await Promise.all([
        loadWebResearchCapability(),
        loadWebReferences(),
        loadMaterials(),
      ])
    } else {
      storedWebReferences.value = []
      await loadMaterials()
    }
    if (targetId && targetId === props.scopeTargetId) {
      const webByMaterialId = new Map(storedWebReferences.value.map(item => [item.material_asset_id, item]))
      const scoped = materials.value.flatMap(item => {
        const usage = item.usages?.find(link => link.target_id === targetId)
        if (!usage) return []
        return [{
          ...item,
          ...(webByMaterialId.get(item.material_asset_id) || {}),
          role: props.variant === 'question-bank'
            ? 'question_source' as const
            : usage.role === 'primary'
              ? 'primary' as const
              : 'reference' as const,
        }]
      })
      if (scoped.length || configuredTargetIds.value.has(targetId)) {
        applySelection(scoped, false)
      } else if (!completedWorkflow.value) {
        const recommended = recommendedSources()
        applySelection(recommended, false)
        if (recommended.length) {
          configuredTargetIds.value.add(targetId)
          await persistScopedSelection(recommended, 'auto')
        }
      }
    }
  }
  finally { loading.value = false; hasLoaded.value = true }
}

async function uploadFiles(files: File[], role: 'primary' | 'reference' | 'question_source') {
  if (!files.length) return
  loading.value = true; error.value = ''
  try {
    const uploaded: CourseReferenceItem[] = []
    for (const file of role === 'primary' ? files.slice(0, 1) : files) {
      const data = new FormData(); data.append('file', file); data.append('course_id', props.courseId)
      const response = await http.post('/api/materials', data, teacherRequestConfig({ headers: { 'Content-Type': 'multipart/form-data' }, silentError: true }))
      const payload = response.data
      if (!payload?.course_space?.course_asset_id) throw new Error(t('courseWorkbench.references.registerFailed', '资料已上传，但未能加入当前课程'))
      uploaded.push({
        package_id: payload.course_space.package_id,
        asset_id: payload.course_space.course_asset_id,
        material_asset_id: payload.asset_id,
        filename: payload.filename,
        relative_path: payload.course_space.relative_path,
        size_bytes: payload.size_bytes || file.size,
        uploaded_at: payload.uploaded_at,
        role,
        processing_status: payload.status,
        parse_status: payload.parse_status,
        parse_error: payload.parse_error,
        parse_warnings: payload.parse_warnings,
      })
    }
    let next = selected.value.filter(item => role !== 'primary' || item.role !== 'primary')
    for (const item of uploaded) next = [...next.filter(current => current.asset_id !== item.asset_id), item]
    commit(next); await loadMaterials()
  } catch (reason: any) { error.value = String(reason?.response?.data?.detail || reason?.message || t('courseWorkbench.references.uploadFailed', '资料上传失败')) }
  finally { loading.value = false }
}

function handleInput(event: Event, role: 'primary' | 'reference' | 'question_source') {
  const input = event.target as HTMLInputElement
  void uploadFiles(Array.from(input.files || []), role)
  input.value = ''
}
function handleDrop(event: DragEvent, role: 'primary' | 'reference' | 'question_source') { dragRole.value = ''; void uploadFiles(Array.from(event.dataTransfer?.files || []), role) }
async function uploadSmartFiles(files: File[]) {
  if (!files.length) return
  let remaining = files
  if (!primarySource.value) {
    await uploadFiles(files.slice(0, 1), 'primary')
    if (!primarySource.value) return
    remaining = files.slice(1)
  }
  if (remaining.length) await uploadFiles(remaining, 'reference')
}
function handleSmartInput(event: Event) {
  const input = event.target as HTMLInputElement
  void uploadSmartFiles(Array.from(input.files || []))
  input.value = ''
}
function handleSmartDrop(event: DragEvent) { dragRole.value = ''; void uploadSmartFiles(Array.from(event.dataTransfer?.files || [])) }
function removeSource(assetId: string) { commit(selected.value.filter(item => item.asset_id !== assetId)) }
function addExisting(item: CourseReferenceItem) { commit([...selected.value, { ...item, role: !primarySource.value ? 'primary' : 'reference' }]) }
function reusePreviousSources() {
  let hasPrimary = selected.value.some(item => item.role === 'primary')
  const reused = previousAvailableSources.value.map(item => {
    const role = item.role === 'primary' && !hasPrimary ? 'primary' as const : 'reference' as const
    if (role === 'primary') hasPrimary = true
    return { ...item, role }
  })
  if (reused.length) commit([...selected.value, ...reused])
}
function handleWebSaved(references: CourseReferenceItem[]) { storedWebReferences.value = references; mergeWebReferences(references); void loadMaterials() }
watch(() => [props.courseId, props.stage, props.lessonId, props.refreshToken], () => {
  sourceEditing.value = false
  hasLoaded.value = false
  void loadAll()
})
watch(() => props.workflowState, (value, previous) => {
  const isCompleted = ['review', 'confirmed'].includes(value)
  const wasCompleted = ['review', 'confirmed'].includes(previous || '')
  if (!isCompleted || !wasCompleted) sourceEditing.value = false
  if (isCompleted && !wasCompleted) void loadAll()
})
watch(
  [sourceOperationBusy, sourceGenerationBlocked, sourceBlockReason],
  () => emit('source-state-change', {
    busy: sourceOperationBusy.value,
    blocked: sourceGenerationBlocked.value,
    reason: sourceBlockReason.value,
  }),
  { immediate: true },
)
onMounted(loadAll)
</script>

<style scoped>
.reference-tray{min-width:0;min-height:0;overflow:auto;border-left:1px solid #e4e9f1;background:#fbfcfe}.reference-tray__header{min-height:54px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 12px 0 16px;border-bottom:1px solid #e7ebf2;background:#fff}.reference-tray__header.is-close-only{justify-content:flex-end}.reference-tray__header strong{color:#243047;font-size:14px}.reference-tray__header button{width:30px;height:30px;display:grid;place-items:center;border:0;border-radius:8px;color:#64748b;background:transparent;cursor:pointer}.reference-tray__header button:hover{color:#334155;background:#f3f5f8}.reference-tray__header button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.system-context{width:calc(100% - 32px);display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:10px;margin:16px 16px 4px;padding:10px 12px;border:1px solid #e2e7ef;border-radius:10px;color:inherit;background:#fff;text-align:left;font:inherit;cursor:pointer}.system-context:hover{border-color:#c9c8f7;background:#fafaff}.system-context:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.system-context>span{width:34px;height:34px;display:grid;place-items:center;border-radius:8px;color:#4f46e5;background:#eef2ff}.system-context strong{min-width:0;overflow:hidden;color:#334155;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.system-context>svg{color:#7b8798}.reference-tray.is-compact .system-context{min-height:46px}.reuse-previous{min-height:34px;display:flex;align-items:center;gap:7px;margin:8px 16px 0;padding:0;border:0;color:#4f46e5;background:transparent;font:inherit;font-size:14px;font-weight:700;cursor:pointer}.reuse-previous small{min-width:20px;height:20px;display:grid;place-items:center;border-radius:10px;color:#4338ca;background:#eef2ff;font-size:14px}.reuse-previous:hover:not(:disabled){color:#3730a3}.reuse-previous:focus-visible{outline:2px solid #6366f1;outline-offset:3px}.reuse-previous:disabled{opacity:.5;cursor:not-allowed}.source-group,.material-library{display:grid;gap:8px;padding:16px 16px 0}.group-heading{display:flex;align-items:center;justify-content:space-between;color:#334155;font-size:14px}.group-heading small{color:#64748b}.drop-zone{min-height:78px;display:flex;align-items:center;gap:10px;padding:10px;border:1px dashed #b9c3d2;border-radius:10px;color:#64748b;background:#fff}.drop-zone.dragging,.reference-add.dragging{border-color:#5b57e8;background:#f4f4ff}.drop-zone.has-file{border-style:solid}.drop-zone>div,.reference-item>div{min-width:0;display:grid;gap:3px;flex:1}.drop-zone strong,.reference-item strong{overflow:hidden;color:#334155;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.drop-zone small,.reference-item small{color:#64748b;font-size:14px}.drop-zone>button:not(.empty-drop),.reference-item>button{width:28px;height:28px;display:grid;place-items:center;border:0;border-radius:6px;color:#64748b;background:transparent;cursor:pointer}.empty-drop{width:100%;min-height:58px;display:flex;align-items:center;justify-content:center;gap:7px;border:0;color:#4f46e5;background:transparent;font-size:14px;font-weight:700;cursor:pointer}.reference-list{display:grid;gap:7px}.reference-item{min-height:54px;display:flex;align-items:center;gap:9px;padding:8px 9px;border:1px solid #e2e7ef;border-radius:9px;background:#fff}.reference-item>svg{color:#6366f1}.reference-add{min-height:42px;display:flex;align-items:center;justify-content:center;gap:7px;border:1px dashed #b9c3d2;border-radius:9px;color:#4f46e5;background:#fff;font-size:14px;font-weight:700;cursor:pointer}.material-library{padding-bottom:18px}.material-library>button{min-height:38px;display:grid;grid-template-columns:18px minmax(0,1fr) 16px;align-items:center;gap:7px;padding:0 9px;border:0;border-radius:7px;color:#475569;background:transparent;text-align:left;cursor:pointer}.material-library>button:hover{background:#eef2ff;color:#4338ca}.material-library>button span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}.material-library>p{margin:3px 0;color:#64748b;font-size:14px}.tray-error{margin:12px 16px;padding:9px 10px;border-radius:8px;color:#b91c1c;background:#fff1f2;font-size:14px}.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.reference-tray__title{min-width:0;display:flex;align-items:center;gap:9px}.reference-tray__title>span{width:30px;height:30px;display:grid;place-items:center;border-radius:8px;color:#4f46e5;background:#eef2ff}.reference-tray__title>div{min-width:0;display:grid;gap:1px}.reference-tray__title small{color:#778397;font-size:14px}.system-context>div{min-width:0;display:grid;gap:2px}.system-context small{color:#788497;font-size:14px}.reference-tray.is-ppt{background:#fff}.ppt-smart-sources{gap:10px}.ppt-smart-source-list{display:grid;gap:7px}.ppt-smart-source-item{min-height:54px;display:grid;grid-template-columns:32px minmax(0,1fr) 28px;align-items:center;gap:8px;padding:7px 8px;border-radius:9px;background:#f7f8fc}.ppt-smart-source-item>span{width:32px;height:32px;display:grid;place-items:center;border-radius:8px;color:#5651ce;background:#ececff}.ppt-smart-source-item>div{min-width:0;display:grid;gap:2px}.ppt-smart-source-item strong{overflow:hidden;color:#303b50;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.ppt-smart-source-item small{color:#788497;font-size:14px}.ppt-smart-source-item>button{width:28px;height:28px;display:grid;place-items:center;border:0;border-radius:7px;color:#7c8798;background:transparent;cursor:pointer}.ppt-smart-source-item>button:hover{color:#334155;background:#e9ebf2}.ppt-smart-empty{min-height:116px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:5px;padding:16px;color:#625dd7;text-align:center}.ppt-smart-empty strong{color:#3b4659;font-size:14px}.ppt-smart-empty span{max-width:230px;color:#788497;font-size:14px;line-height:1.5}.ppt-smart-actions{display:grid;grid-template-columns:1fr 1fr;gap:7px}.ppt-smart-actions button{min-height:40px;display:flex;align-items:center;justify-content:center;gap:6px;border:1px solid #dce1e9;border-radius:9px;color:#4d596e;background:#fff;font-size:14px;font-weight:700;cursor:pointer}.ppt-smart-actions button:hover{border-color:#aaa7e8;color:#37348c;background:#fafaff}.ppt-smart-actions button.dragging{border-color:#5b57e8;background:#f4f4ff}.ppt-smart-actions button:focus-visible,.ppt-smart-source-item>button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.source-group--web{padding-top:18px}.web-source-list{display:grid;gap:7px}.web-source-item{min-height:56px;display:grid;grid-template-columns:18px minmax(0,1fr) 28px;align-items:center;gap:9px;padding:8px 9px;border:1px solid #dce5f0;border-radius:9px;background:#fff}.web-source-item>svg{color:#0f766e}.web-source-item>div{min-width:0;display:grid;gap:3px}.web-source-item strong{overflow:hidden;color:#334155;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.web-source-item a{display:flex;align-items:center;gap:4px;overflow:hidden;color:#0f766e;font-size:14px;text-decoration:none;text-overflow:ellipsis;white-space:nowrap}.web-source-item small{color:#64748b;font-size:14px}.web-source-item>button{width:28px;height:28px;display:grid;place-items:center;border:0;border-radius:6px;color:#64748b;background:transparent;cursor:pointer}.web-research-open{min-height:42px;display:flex;align-items:center;justify-content:center;gap:7px;border:1px dashed #8fbab5;border-radius:9px;color:#0f766e;background:#f4fbfa;font-size:14px;font-weight:750;cursor:pointer}
.reference-tray.is-question-bank{height:100%;overflow:auto;border-left:0;background:#fbfcfe}.reference-tray.is-question-bank .reference-tray__header{min-height:64px;background:#fbfcfe}.source-group--question-bank{gap:10px;padding:12px 14px 18px}.source-group--question-bank .reference-list{gap:0}.source-group--question-bank .reference-item{min-height:48px;padding:7px 2px;border:0;border-bottom:1px solid #e7ebf2;border-radius:0;background:transparent}.reference-tray.is-question-bank .reference-add{min-height:38px;margin-top:0;border:0;border-radius:8px;color:#5552c8;background:#f0f1ff}.reference-tray.is-question-bank .reference-item~.reference-add{margin-top:10px}.reference-tray.is-question-bank .reference-add:hover{color:#4338ca;background:#e7e8ff}
.reference-interactive{padding-bottom:18px}.source-status{display:grid;grid-template-columns:32px minmax(0,1fr);align-items:center;gap:9px;margin:12px 16px 0;padding:10px 11px;border:1px solid #dfe5ef;border-radius:10px;background:#fff}.source-status>span{width:32px;height:32px;display:grid;place-items:center;border-radius:8px;color:#5651ce;background:#eef0ff}.source-status>div{min-width:0;display:grid;gap:3px}.source-status strong{color:#334155;font-size:14px}.source-status small{color:#738095;font-size:14px;line-height:1.45}.source-status--completed{border-color:#cfe9d8;background:#f7fcf9}.source-status--completed>span{color:#168044;background:#e7f7ed}.source-status--failed{border-color:#f1cdd1;background:#fff8f8}.source-status--failed>span{color:#b9404e;background:#fdebed}.reference-workflow-action{padding:12px 16px 2px}.workflow-state{display:grid;gap:14px;margin:12px 16px 18px;padding:14px;border:1px solid #dadcf6;border-radius:12px;background:linear-gradient(150deg,#fbfbff,#f4f5ff);box-shadow:0 10px 28px rgba(70,69,151,.08)}.workflow-state>header{display:grid;grid-template-columns:38px minmax(0,1fr);align-items:center;gap:10px}.workflow-state__signal{width:38px;height:38px;display:grid;place-items:center;border-radius:10px;color:#fff;background:#5955d8;box-shadow:0 7px 18px rgba(89,85,216,.22)}.workflow-state>header>div{min-width:0;display:grid;gap:4px}.workflow-state>header strong{color:#2d3650;font-size:14px}.workflow-state>header small{color:#6f7b90;font-size:14px;line-height:1.45}.workflow-state--paused{border-color:#eadfbd;background:linear-gradient(150deg,#fffdf8,#fff9e9)}.workflow-state--paused .workflow-state__signal{color:#8a5d09;background:#f6df9f;box-shadow:none}.workflow-progress{height:5px;overflow:hidden;border-radius:3px;background:#e3e5f4}.workflow-progress i{position:relative;width:100%;height:100%;display:block;transform-origin:left center;border-radius:inherit;background:#5955d8;transition:transform .25s cubic-bezier(.2,.8,.2,1)}.workflow-state--generating .workflow-progress i::after{position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.72),transparent);animation:workflow-scan 1.6s ease-in-out infinite;content:""}.workflow-state--paused .workflow-progress i{background:#d39b2f}.workflow-source-list{display:grid;gap:7px;margin:0;padding:0;list-style:none}.workflow-source-list li{min-height:52px;display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:8px;padding:7px 8px;border:1px solid rgba(213,216,239,.9);border-radius:9px;background:rgba(255,255,255,.8)}.workflow-source-pulse{width:32px;height:32px;display:grid;place-items:center;border-radius:8px;color:#5551ce;background:#ececff}.workflow-state--generating .workflow-source-pulse{animation:source-usage-pulse 1.8s ease-in-out infinite}.workflow-source-list li>div{min-width:0;display:grid;gap:2px}.workflow-source-list strong{overflow:hidden;color:#354056;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.workflow-source-list small{color:#7a8699;font-size:14px}.workflow-source-list em{color:#5b57c8;font-size:14px;font-style:normal;font-weight:750}.workflow-state--paused .workflow-source-list em{color:#956b19}.workflow-no-sources{margin:0;color:#6f7b90;font-size:14px;line-height:1.55}.workflow-state>footer{display:flex;align-items:center;gap:7px}.workflow-state>footer button{min-height:34px;display:flex;align-items:center;justify-content:center;gap:6px;padding:0 10px;border:1px solid #d5d9e5;border-radius:8px;color:#596579;background:#fff;font-size:14px;font-weight:700;cursor:pointer}.workflow-state>footer button:hover{border-color:#aaa7e8;color:#37348c;background:#fafaff}.workflow-state>footer .workflow-resume{border-color:#5651d1;color:#fff;background:#5651d1}.workflow-state>footer .workflow-resume:hover{border-color:#4742ba;color:#fff;background:#4742ba}.workflow-spinner{animation:spin 1s linear infinite}.tray-mode-enter-active,.tray-mode-leave-active{transition:opacity .2s ease,transform .2s cubic-bezier(.2,.8,.2,1),clip-path .2s ease}.tray-mode-enter-from{opacity:0;transform:translateY(8px);clip-path:inset(0 0 10% 0)}.tray-mode-leave-to{opacity:0;transform:translateY(-6px);clip-path:inset(0 0 10% 0)}.drop-zone button:disabled,.reference-add:disabled,.ppt-smart-actions button:disabled,.material-library>button:disabled,.web-research-open:disabled{opacity:.48;cursor:not-allowed}.drop-zone>button:not(.empty-drop):hover,.reference-item>button:hover,.web-source-item>button:hover{color:#334155;background:#eef1f6}.empty-drop:focus-visible,.reference-add:focus-visible,.material-library>button:focus-visible,.web-research-open:focus-visible,.workflow-state>footer button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}@keyframes workflow-scan{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}@keyframes source-usage-pulse{0%,100%{box-shadow:0 0 0 0 rgba(89,85,216,0)}50%{box-shadow:0 0 0 4px rgba(89,85,216,.1)}}@keyframes spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.workflow-spinner,.workflow-state--generating .workflow-progress i::after,.workflow-state--generating .workflow-source-pulse{animation:none}.tray-mode-enter-active,.tray-mode-leave-active,.workflow-progress i{transition:none}}
.workflow-sources{display:grid;gap:10px;margin:10px 16px 18px;padding:2px 0}.workflow-source-list--quiet li{grid-template-columns:32px minmax(0,1fr);border-color:#e5e9ef;background:#fff}.workflow-source-list--quiet .workflow-source-pulse{color:#6268a6;background:#f0f1f7}
.source-status>.source-status__actions{grid-column:2;display:flex;align-items:center;flex-wrap:wrap;gap:7px}.source-status__actions button,.current-source-actions button{min-height:30px;display:inline-flex;align-items:center;justify-content:center;gap:5px;padding:0 9px;border-radius:7px;font-size:14px;font-weight:750;cursor:pointer}.source-status__retry{border:1px solid #dc9da5;color:#a73341;background:#fff}.source-status__retry:hover{border-color:#b9404e;background:#fff1f2}.source-status__regenerate{border:1px solid #5651d1;color:#fff;background:#5651d1}.source-status__regenerate:hover:not(:disabled){border-color:#4742ba;background:#4742ba}.source-status__regenerate:disabled{opacity:.48;cursor:not-allowed}.source-status__collapse{border:1px solid #cfd4df;color:#596579;background:#fff}.source-status__collapse:hover{border-color:#aaa7e8;color:#37348c;background:#fafaff}.source-status__actions button:focus-visible,.current-source-actions button:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.source-status--completed.is-editing{border-color:#dfe5ef;background:#fff}.source-status--completed.is-editing>span{color:#5651ce;background:#eef0ff}.source-status.is-dirty{border-color:#ead8a5;background:#fffaf0}.source-status.is-dirty>span{color:#94630c;background:#fff0c7}.current-source-summary{display:grid;gap:10px;padding:16px}.current-source-list{display:grid;gap:7px;margin:0;padding:0;list-style:none}.current-source-list li{min-height:52px;display:grid;grid-template-columns:32px minmax(0,1fr) 18px;align-items:center;gap:8px;padding:7px 8px;border:1px solid #e2e7ef;border-radius:9px;background:#fff}.current-source-list li>span{width:32px;height:32px;display:grid;place-items:center;border-radius:8px;color:#5651ce;background:#eef0ff}.current-source-list li>div{min-width:0;display:grid;gap:2px}.current-source-list strong{overflow:hidden;color:#334155;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.current-source-list small{color:#738095;font-size:14px}.current-source-list li>svg{color:#168044}.current-source-actions{display:grid;gap:8px}.current-source-adjust{min-height:38px;display:flex;align-items:center;justify-content:center;gap:7px;border:1px solid #d7dbe6;border-radius:9px;color:#4d596e;background:#fff;font-size:14px;font-weight:700;cursor:pointer}.current-source-adjust:hover{border-color:#aaa7e8;color:#37348c;background:#fafaff}.current-source-adjust:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.current-source-hint{color:#788497;font-size:14px;line-height:1.55}
.source-status--loading{margin-bottom:18px}.source-status--sources-processing{border-color:#dcdcf4;background:#fafaff}.source-status--sources-processing>span{color:#5651ce;background:#eeeeff}.source-status--sources-failed,.source-status.is-dirty.source-status--sources-failed{border-color:#f1cdd1;background:#fff8f8}.source-status--sources-failed>span,.source-status.is-dirty.source-status--sources-failed>span{color:#b9404e;background:#fdebed}.source-status__actions button:disabled,.current-source-adjust:disabled{opacity:.48;cursor:not-allowed}.source-status__retry:hover:not(:disabled){border-color:#b9404e;background:#fff1f2}.current-source-adjust:hover:not(:disabled){border-color:#aaa7e8;color:#37348c;background:#fafaff}
.reference-scope{display:grid;gap:9px;margin:12px 16px 0;padding:11px;border:1px solid #dfe5ef;border-radius:10px;background:#fff}
.reference-scope>header{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.reference-scope>header>div{min-width:0;display:grid;gap:3px}
.reference-scope>header strong{color:#334155;font-size:14px;font-weight:750}
.reference-scope>header small{overflow:hidden;color:#738095;font-size:14px;line-height:1.35;text-overflow:ellipsis;white-space:nowrap}
.reference-scope>header>span{flex:none;display:flex;align-items:center;gap:4px;color:#6965b9;font-size:13px;font-weight:700}
.reference-scope__list{display:grid;gap:10px;margin:0;padding:0;list-style:none}
.reference-scope__list>li{display:grid;gap:8px;padding-top:10px;border-top:1px solid #edf0f5}
.reference-scope__file{min-width:0;display:grid;gap:2px}
.reference-scope__file strong{overflow:hidden;color:#3f4b60;font-size:14px;text-overflow:ellipsis;white-space:nowrap}
.reference-scope__file small{color:#738095;font-size:13px;line-height:1.35}
.reference-scope__list>li>label>select,.reference-scope__range select{width:100%;min-height:36px;padding:0 30px 0 9px;border:1px solid #d3dae5;border-radius:8px;color:#3f4b60;background:#fff;font:inherit;font-size:14px}
.reference-scope__range{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;gap:6px;color:#8a96a8}
.reference-scope__custom{max-height:188px;display:grid;gap:2px;overflow:auto;padding:3px}
.reference-scope__custom label{min-height:34px;display:grid;grid-template-columns:18px minmax(0,1fr);align-items:center;gap:7px;padding:0 6px;border-radius:7px;color:#596579;font-size:14px;cursor:pointer}
.reference-scope__custom label:hover{background:#f5f6fa}
.reference-scope__custom input{accent-color:#5b57e8}
.reference-scope__custom span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.reference-scope__apply{min-height:36px;display:flex;align-items:center;justify-content:center;gap:6px;border:1px solid #c9c7ee;border-radius:8px;color:#4338ca;background:#f7f7ff;font-size:14px;font-weight:750;cursor:pointer}
.reference-scope__apply:hover:not(:disabled){border-color:#aaa7e8;background:#eeeeff}
.reference-scope__apply:focus-visible,.reference-scope select:focus-visible,.reference-scope__custom input:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}
.reference-scope__apply:disabled{opacity:.48;cursor:not-allowed}
.reference-scope.is-locked{background:#f7f8fb}
</style>
