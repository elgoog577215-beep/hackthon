<template>
  <Teleport to="body">
    <div v-if="modelValue" class="generation-dialog-layer" @keydown.esc="close">
      <button
        type="button"
        class="generation-dialog-backdrop"
        :aria-label="t('common.cancel', '取消')"
        @click="close"
      />
      <section
        ref="dialogRef"
        class="generation-dialog"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
      >
        <header class="generation-dialog__header">
          <div class="generation-dialog__heading">
            <span class="generation-dialog__mark"><Sparkles :size="18" /></span>
            <div>
              <p>{{ t('courseGeneration.dialog.eyebrow', '创建学习课程') }}</p>
              <h2 :id="titleId">{{ t('courseGeneration.dialog.title', 'AI 智能课程生成') }}</h2>
            </div>
          </div>
          <button type="button" class="icon-button" :title="t('common.cancel', '取消')" @click="close">
            <X :size="18" />
          </button>
        </header>

        <form class="generation-dialog__body" @submit.prevent="submit">
          <section class="form-section form-section--lead course-type-section">
            <fieldset class="choice-group">
              <legend class="choice-group__title">
                <span class="field-icon field-icon--rose"><Route :size="14" /></span>
                <span>
                  {{ t('courseGeneration.courseTypes.label', '课程类型') }}
                  <small>{{ t('courseGeneration.courseTypes.help', '课程类型决定学习过程如何组织；学科决定内容如何讲解。') }}</small>
                </span>
              </legend>
              <div class="course-type-options">
                <button
                  v-for="item in courseTypeOptions"
                  :key="item.value"
                  type="button"
                  class="course-type-option"
                  :class="{ active: form.courseType === item.value }"
                  :data-course-type="item.value"
                  :aria-pressed="form.courseType === item.value"
                  :disabled="busy || !item.available"
                  @click="selectCourseType(item.value)"
                >
                  <span class="course-type-option__icon"><component :is="item.icon" :size="18" /></span>
                  <span class="course-type-option__copy">
                    <span class="course-type-option__heading">
                      <strong>{{ item.label }}</strong>
                    </span>
                    <span>{{ item.detail }}</span>
                  </span>
                  <span v-if="item.available" class="course-type-option__check"><Check :size="11" /></span>
                </button>
              </div>
            </fieldset>
          </section>

          <section v-if="form.courseType === 'systematic'" class="form-section intent-section">
            <label class="field-label" for="course-subject">
              {{ t('courseGeneration.form.topic', '课程主题') }}
            </label>
            <input
              id="course-subject"
              v-model="form.systematicTopic"
              class="text-input text-input--large"
              type="text"
              autocomplete="off"
              maxlength="200"
              :placeholder="t('courseGeneration.form.topicPlaceholder', '例如：线性代数基础')"
              :disabled="busy"
              autofocus
            />
            <p class="field-help">{{ t('courseGeneration.dialog.topicHelp', '写清楚学习对象；难度、结构和资料边界在下方单独控制。') }}</p>
          </section>

          <section v-else-if="form.courseType === 'project'" class="form-section intent-section project-intent" data-testid="project-intent-form">
            <div class="project-intent__heading">
              <div>
                <strong>{{ t('courseGeneration.project.title', '定义你的实战项目') }}</strong>
                <span>{{ t('courseGeneration.project.help', '先明确要完成的成果，再结合你的起点生成项目里程碑和个人学习路径。') }}</span>
              </div>
              <Target :size="18" />
            </div>
            <div class="project-fields">
              <label class="project-field project-field--wide" for="project-goal">
                <span class="field-label">{{ t('courseGeneration.project.goalLabel', '想完成什么项目？') }}</span>
                <input
                  id="project-goal"
                  v-model="form.projectGoal"
                  class="text-input text-input--large"
                  type="text"
                  autocomplete="off"
                  required
                  maxlength="200"
                  :placeholder="t('courseGeneration.project.goalPlaceholder', '例如：设计一款适合大学生使用的环保保温玻璃杯')"
                  :disabled="busy"
                />
              </label>
              <label class="project-field project-field--wide" for="project-deliverable">
                <span class="field-label">{{ t('courseGeneration.project.deliverableLabel', '最终需要交付什么？') }}</span>
                <input
                  id="project-deliverable"
                  v-model="form.expectedDeliverable"
                  class="text-input"
                  type="text"
                  autocomplete="off"
                  required
                  maxlength="3000"
                  :placeholder="t('courseGeneration.project.deliverablePlaceholder', '例如：一份产品设计方案和可验证原型')"
                  :disabled="busy"
                />
              </label>
              <label class="project-field" for="project-prior-experience">
                <span class="field-label">{{ t('courseGeneration.project.experienceLabel', '已经有哪些相关经验？') }}</span>
                <textarea
                  id="project-prior-experience"
                  v-model="form.priorExperience"
                  class="textarea-input textarea-input--compact"
                  maxlength="3000"
                  :placeholder="t('courseGeneration.project.experiencePlaceholder', '例如：学过产品设计，熟悉造型和结构')"
                  :disabled="busy"
                />
              </label>
              <label class="project-field" for="project-current-uncertainty">
                <span class="field-label">{{ t('courseGeneration.project.uncertaintyLabel', '当前最不确定什么？') }}</span>
                <textarea
                  id="project-current-uncertainty"
                  v-model="form.currentUncertainty"
                  class="textarea-input textarea-input--compact"
                  maxlength="3000"
                  :placeholder="t('courseGeneration.project.uncertaintyPlaceholder', '例如：不了解玻璃材料、隔热原理和制造工艺')"
                  :disabled="busy"
                />
              </label>
            </div>
            <p class="starting-point-note">
              <Info :size="15" />
              <span>
                <strong>{{ hasStartingPointInput ? t('courseGeneration.project.startingPointTitle', '暂定学习起点') : t('courseGeneration.project.insufficientTitle', '起点信息可暂时跳过') }}</strong>
                {{ hasStartingPointInput
                  ? t('courseGeneration.project.startingPointHelp', '系统会根据你的自述形成第一版个人路径，并在后续学习中继续验证和调整。')
                  : t('courseGeneration.project.insufficientHelp', '不填写也可以生成；系统会标记起点信息不足，先给出暂定路径，再根据后续学习行为调整。') }}
              </span>
            </p>
          </section>

          <section v-else-if="form.courseType === 'inquiry'" class="form-section intent-section project-intent" data-testid="inquiry-intent-form">
            <div class="project-intent__heading">
              <div>
                <strong>{{ t('courseGeneration.inquiry.title', '定义要探究的问题') }}</strong>
                <span>{{ t('courseGeneration.inquiry.help', '先明确核心问题和结论形态，课程会沿子问题、证据与反例逐步推进。') }}</span>
              </div>
              <MessageCircleQuestion :size="18" />
            </div>
            <div class="project-fields">
              <label class="project-field project-field--wide" for="inquiry-core-question">
                <span class="field-label">{{ t('courseGeneration.inquiry.questionLabel', '你真正想回答什么问题？') }}</span>
                <input
                  id="inquiry-core-question"
                  v-model="form.coreQuestion"
                  class="text-input text-input--large"
                  type="text"
                  autocomplete="off"
                  required
                  maxlength="200"
                  :placeholder="t('courseGeneration.inquiry.questionPlaceholder', '例如：生成式 AI 会如何改变大学的教学与评价？')"
                  :disabled="busy"
                />
              </label>
              <label class="project-field project-field--wide" for="inquiry-desired-output">
                <span class="field-label">{{ t('courseGeneration.inquiry.outputLabel', '最终希望形成什么结论？') }}</span>
                <input
                  id="inquiry-desired-output"
                  v-model="form.desiredOutput"
                  class="text-input"
                  type="text"
                  autocomplete="off"
                  required
                  maxlength="3000"
                  :placeholder="t('courseGeneration.inquiry.outputPlaceholder', '例如：一份区分适用条件、风险与证据强度的判断报告')"
                  :disabled="busy"
                />
              </label>
              <label class="project-field" for="inquiry-understanding">
                <span class="field-label">{{ t('courseGeneration.inquiry.understandingLabel', '你目前怎么看？') }}</span>
                <textarea
                  id="inquiry-understanding"
                  v-model="form.existingUnderstanding"
                  class="textarea-input textarea-input--compact"
                  maxlength="3000"
                  :placeholder="t('courseGeneration.inquiry.understandingPlaceholder', '写下当前判断或尚未验证的假设')"
                  :disabled="busy"
                />
              </label>
              <label class="project-field" for="inquiry-evidence-scope">
                <span class="field-label">{{ t('courseGeneration.inquiry.evidenceLabel', '证据范围与边界') }}</span>
                <textarea
                  id="inquiry-evidence-scope"
                  v-model="form.evidenceScope"
                  class="textarea-input textarea-input--compact"
                  maxlength="3000"
                  :placeholder="t('courseGeneration.inquiry.evidencePlaceholder', '例如：优先使用近三年的高校实践、研究论文与公开政策')"
                  :disabled="busy"
                />
              </label>
            </div>
            <p class="starting-point-note">
              <Info :size="15" />
              <span>
                <strong>{{ t('courseGeneration.inquiry.noteTitle', '已有认识会作为待检验假设') }}</strong>
                {{ t('courseGeneration.inquiry.noteHelp', '系统不会把你的初始观点当成事实；目录会保留证据搜集、反例检验和结论边界。') }}
              </span>
            </p>
          </section>

          <section v-else class="form-section intent-section project-intent" data-testid="exam-intent-form">
            <div class="project-intent__heading">
              <div>
                <strong>{{ t('courseGeneration.exam.title', '定义你的冲刺目标') }}</strong>
                <span>{{ t('courseGeneration.exam.help', '明确考试、日期和范围，课程会按剩余时间与薄弱点安排优先级。') }}</span>
              </div>
              <Timer :size="18" />
            </div>
            <div class="project-fields">
              <label class="project-field" for="exam-name">
                <span class="field-label">{{ t('courseGeneration.exam.nameLabel', '准备什么考试？') }}</span>
                <input
                  id="exam-name"
                  v-model="form.examName"
                  class="text-input text-input--large"
                  type="text"
                  autocomplete="off"
                  required
                  maxlength="200"
                  :placeholder="t('courseGeneration.exam.namePlaceholder', '例如：大学英语六级考试')"
                  :disabled="busy"
                />
              </label>
              <label class="project-field" for="exam-date">
                <span class="field-label">{{ t('courseGeneration.exam.dateLabel', '考试日期') }}</span>
                <input
                  id="exam-date"
                  v-model="form.examDate"
                  class="text-input text-input--large"
                  type="date"
                  required
                  :min="todayIso"
                  :disabled="busy"
                />
              </label>
              <label class="project-field project-field--wide" for="exam-scope">
                <span class="field-label">{{ t('courseGeneration.exam.scopeLabel', '考纲与考试范围') }}</span>
                <textarea
                  id="exam-scope"
                  v-model="form.examScope"
                  class="textarea-input textarea-input--compact"
                  required
                  maxlength="5000"
                  :placeholder="t('courseGeneration.exam.scopePlaceholder', '例如：听力、阅读、翻译和写作；重点覆盖历年高频题型')"
                  :disabled="busy"
                />
              </label>
              <label class="project-field project-field--wide" for="exam-preparation">
                <span class="field-label">{{ t('courseGeneration.exam.preparationLabel', '当前准备情况与薄弱点') }}</span>
                <textarea
                  id="exam-preparation"
                  v-model="form.currentPreparation"
                  class="textarea-input textarea-input--compact"
                  maxlength="3000"
                  :placeholder="t('courseGeneration.exam.preparationPlaceholder', '例如：阅读稳定，听力长对话和写作论证较弱，每周可投入 8 小时')"
                  :disabled="busy"
                />
              </label>
            </div>
            <p class="starting-point-note">
              <Info :size="15" />
              <span>
                <strong>{{ t('courseGeneration.exam.noteTitle', '先定优先级，再用练习校准') }}</strong>
                {{ t('courseGeneration.exam.noteHelp', '自述薄弱点只决定首轮安排；诊断题和模拟任务会继续修正复习重点。') }}
              </span>
            </p>
          </section>

          <section class="form-section teacher-brief-section" data-testid="teacher-course-brief-form">
            <div class="teacher-brief-section__heading">
              <div>
                <strong>{{ t('courseGeneration.teacherBrief.title', '课堂交付约束') }}</strong>
                <span>{{ t('courseGeneration.teacherBrief.help', '这些信息会写入课程生成契约，并成为全课教案的可审阅字段。') }}</span>
              </div>
              <Target :size="18" />
            </div>
            <div class="teacher-brief-section__core">
              <label for="teacher-target-audience">
                <span class="field-label">{{ t('courseGeneration.teacherBrief.targetAudience', '教学对象') }}</span>
                <input id="teacher-target-audience" v-model="form.targetAudience" class="text-input" type="text" maxlength="500" :disabled="busy" />
              </label>
              <label for="teacher-total-hours">
                <span class="field-label">{{ t('courseGeneration.teacherBrief.totalHours', '总课时') }}</span>
                <input id="teacher-total-hours" v-model.number="form.totalClassHours" class="text-input" type="number" min="1" max="1000" step="1" :disabled="busy" />
              </label>
              <label for="teacher-lesson-minutes">
                <span class="field-label">{{ t('courseGeneration.teacherBrief.lessonMinutes', '每次课时长（分钟）') }}</span>
                <input id="teacher-lesson-minutes" v-model.number="form.lessonDurationMinutes" class="text-input" type="number" min="20" max="240" step="1" :disabled="busy" />
              </label>
              <label for="teacher-context">
                <span class="field-label">{{ t('courseGeneration.teacherBrief.context', '授课场景') }}</span>
                <select id="teacher-context" v-model="form.teachingContext" class="select-input" :disabled="busy">
                  <option value="classroom">{{ t('courseGeneration.teacherBrief.contextClassroom', '线下课堂') }}</option>
                  <option value="online">{{ t('courseGeneration.teacherBrief.contextOnline', '在线授课') }}</option>
                  <option value="blended">{{ t('courseGeneration.teacherBrief.contextBlended', '混合式授课') }}</option>
                  <option value="self_study">{{ t('courseGeneration.teacherBrief.contextSelfStudy', '自主学习') }}</option>
                </select>
              </label>
            </div>
            <details class="teacher-brief-section__advanced">
              <summary>{{ t('courseGeneration.teacherBrief.advancedSettings', '更多课堂设置') }}</summary>
              <div class="teacher-brief-section__advanced-body">
                <div class="teacher-brief-section__advanced-grid">
                  <label for="teacher-academic-term">
                    <span class="field-label">{{ t('courseGeneration.teacherBrief.academicTerm', '开课学期') }}</span>
                    <input id="teacher-academic-term" v-model="form.academicTerm" class="text-input" type="text" maxlength="100" :placeholder="t('courseGeneration.teacherBrief.academicTermPlaceholder', '例如：2026-2027 学年第一学期')" :disabled="busy" />
                  </label>
                  <label for="teacher-class-size">
                    <span class="field-label">{{ t('courseGeneration.teacherBrief.classSize', '预计班级人数') }}</span>
                    <input id="teacher-class-size" v-model.number="form.classSize" class="text-input" type="number" min="1" max="1000" step="1" :disabled="busy" />
                  </label>
                  <label for="teacher-chapter-count">
                    <span class="field-label">{{ t('courseGeneration.teacherBrief.chapterCount', '预计章节数') }}</span>
                    <input id="teacher-chapter-count" v-model.number="form.chapterCount" class="text-input" type="number" min="1" max="100" step="1" :disabled="busy" />
                  </label>
                  <label for="teacher-section-count">
                    <span class="field-label">{{ t('courseGeneration.teacherBrief.sectionCount', '预计小节数') }}</span>
                    <input id="teacher-section-count" v-model.number="form.sectionCount" class="text-input" type="number" min="1" max="500" step="1" :disabled="busy" />
                  </label>
                </div>
                <label class="teacher-brief-section__profile" for="teacher-class-profile">
                  <span class="field-label">{{ t('courseGeneration.teacherBrief.classProfile', '班级与学情特点') }}</span>
                  <textarea id="teacher-class-profile" v-model="form.classProfile" class="textarea-input textarea-input--compact" maxlength="2000" :placeholder="t('courseGeneration.teacherBrief.classProfilePlaceholder', '例如：多数学生已完成先修课，但概念迁移和小组讨论经验有限')" :disabled="busy" />
                </label>
              </div>
            </details>
          </section>

          <section class="form-section course-basis-section">
            <header class="course-basis-section__heading">
              <div>
                <strong>{{ t('courseGeneration.sources.title', '课程依据') }}</strong>
                <span>{{ t('courseGeneration.sources.help', '上传已有资料，或允许系统联网补齐资料没有覆盖的知识。') }}</span>
              </div>
              <Library :size="18" />
            </header>
            <label class="web-enrichment-setting__control course-basis-section__web">
              <input
                v-model="form.retrievalEnabled"
                data-testid="web-retrieval"
                type="checkbox"
                :disabled="busy"
              />
              <span>
                <strong>{{ t('courseGeneration.retrieval.label', '联网研究') }}</strong>
                <small>{{ t('courseGeneration.retrieval.help', '用于新课程蓝图、正文和题库的同源资料核验；默认关闭，不会发送学生画像、作答或个人记录。') }}</small>
              </span>
            </label>
            <div class="material-section">
              <MaterialInputPanel ref="materialInputRef" v-model="materials" :disabled="busy" />
            </div>
          </section>

          <details class="form-section generation-advanced-settings">
            <summary>
              <span>
                <strong>{{ t('courseGeneration.advanced.title', '生成偏好与额外要求') }}</strong>
                <small>{{ t('courseGeneration.advanced.help', '难度、学科讲法、题目策略和其他可选设置') }}</small>
              </span>
              <span>{{ t('courseGeneration.advanced.optional', '可选') }}</span>
            </summary>
            <div class="generation-advanced-settings__body">
              <section class="teaching-settings">
                <div class="teaching-settings__core teaching-settings__core--common">
                  <fieldset class="choice-group difficulty-group">
                    <legend class="choice-group__title">
                      <span class="field-icon field-icon--amber"><Trophy :size="14" /></span>
                      {{ t('courseGeneration.form.difficulty', '难度等级') }}
                    </legend>
                    <div class="difficulty-options">
                      <button
                        v-for="item in difficultyOptions"
                        :key="item.value"
                        type="button"
                        class="difficulty-option"
                        :class="{ active: form.difficulty === item.value }"
                        :data-tone="item.tone"
                        :aria-pressed="form.difficulty === item.value"
                        :disabled="busy"
                        @click="form.difficulty = item.value"
                      >
                        <span class="difficulty-option__rail" />
                        <span class="difficulty-option__copy">
                          <strong>{{ item.label }}</strong>
                          <small>{{ item.detail }}</small>
                        </span>
                        <span class="difficulty-option__check"><Check :size="12" /></span>
                      </button>
                    </div>
                  </fieldset>

                  <div class="strategy-settings">
                    <div class="strategy-settings__heading">
                      <strong>{{ t('courseGeneration.form.strategy', '课程策略') }}</strong>
                      <span>{{ t('courseGeneration.form.strategyHelp', '设置适合内容的学科讲法，以及资料在生成中的作用。') }}</span>
                    </div>
                    <div class="compact-grid">
                      <label>
                        <span class="field-label"><Route :size="13" />{{ t('courseGeneration.pedagogy.label', '主学科结构') }}</span>
                        <select v-model="form.pedagogyMode" class="select-input" :disabled="busy">
                          <option v-for="item in pedagogyOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
                        </select>
                      </label>
                      <label>
                        <span class="field-label"><Network :size="13" />{{ t('courseGeneration.pedagogy.secondaryLabel', '辅助学科') }}</span>
                        <select v-model="form.secondaryMode" data-testid="secondary-pedagogy-mode" class="select-input" :disabled="busy">
                          <option v-for="item in secondaryPedagogyOptions" :key="item.value || 'none'" :value="item.value">{{ item.label }}</option>
                        </select>
                      </label>
                      <label>
                        <span class="field-label"><BookMarked :size="13" />{{ t('courseGeneration.grounding.label', '资料使用边界') }}</span>
                        <select v-model="form.groundingStrategy" class="select-input" :disabled="busy">
                          <option value="material_first">{{ t('courseGeneration.grounding.materialFirst', '资料优先') }}</option>
                          <option value="strict_grounded">{{ t('courseGeneration.grounding.strict', '仅依据资料') }}</option>
                          <option value="general_assisted">{{ t('courseGeneration.grounding.general', '资料与通用知识结合') }}</option>
                        </select>
                      </label>
                    </div>
                  </div>
                </div>
              </section>

              <section class="generation-advanced-settings__assessment">
                <AssessmentGenerationProfileSelector
                  v-model="form.assessmentGenerationProfile"
                  :disabled="busy"
                />
              </section>

              <section>
                <label class="field-label" for="course-requirements">{{ t('courseGeneration.form.requirements', '额外要求') }}</label>
                <textarea
                  id="course-requirements"
                  v-model="form.requirements"
                  class="textarea-input"
                  :disabled="busy"
                  :placeholder="t('courseGeneration.form.requirementsPlaceholder', '例如：多一些推导过程，并给出可独立完成的练习')"
                />
              </section>
            </div>
          </details>

          <section
            v-if="preflight"
            class="generation-preflight"
            :class="`generation-preflight--${preflight.status}`"
            data-testid="generation-preflight"
            aria-live="polite"
          >
            <div class="generation-preflight__summary">
              <span class="generation-preflight__icon">
                <CheckCircle2 v-if="preflight.status === 'ready'" :size="17" />
                <TriangleAlert v-else :size="17" />
              </span>
              <div>
                <strong>{{ preflightTitle }}</strong>
                <span>{{ preflightSummary }}</span>
              </div>
              <small>{{ preflight.capacity?.estimated_sections || 0 }} {{ t('courseGeneration.preflight.sections', '节') }}</small>
            </div>
            <div class="generation-preflight__facts">
              <span>{{ t('courseGeneration.preflight.provider', '模型路线') }} · {{ providerRouteLabel(preflight.provider?.active_route) }}</span>
              <span>{{ t('courseGeneration.preflight.materials', '资料可读') }} · {{ preflight.materials?.readable || 0 }}/{{ preflight.materials?.count || 0 }}</span>
              <span>{{ t('courseGeneration.preflight.concurrency', '建议并发') }} · {{ preflight.capacity?.recommended_concurrency || 1 }}</span>
            </div>
            <ul v-if="preflight.issues.length" class="generation-preflight__issues">
              <li v-for="issue in preflight.issues" :key="`${issue.code}-${issue.item_id || ''}`">
                <strong>{{ preflightIssueMessage(issue.code, issue.message) }}</strong>
                <span>{{ preflightIssueAction(issue.code, issue.action) }}</span>
              </li>
            </ul>
          </section>
        </form>

        <footer class="generation-dialog__footer">
          <div>
            <Library :size="15" />
            <span>{{ t('courseGeneration.progressVaries', '耗时取决于资料数量与解析复杂度') }}</span>
          </div>
          <div class="footer-actions">
            <button type="button" class="secondary-button" :disabled="busy" @click="close">
              {{ t('common.cancel', '取消') }}
            </button>
            <button type="button" class="primary-button" :disabled="!canSubmit" @click="submit">
              <LoaderCircle v-if="busy" class="spin" :size="16" />
              <Sparkles v-else :size="16" />
              {{ submitLabel }}
            </button>
          </div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import {
  BookMarked,
  BookOpen,
  Check,
  CheckCircle2,
  Hammer,
  Info,
  Library,
  LoaderCircle,
  MessageCircleQuestion,
  Network,
  Route,
  Sparkles,
  Target,
  Timer,
  TriangleAlert,
  Trophy,
  X,
} from 'lucide-vue-next'
import MaterialInputPanel from './MaterialInputPanel.vue'
import http from '@/utils/http'
import { t } from '@/shared/i18n'
import AssessmentGenerationProfileSelector from './AssessmentGenerationProfileSelector.vue'
import {
  PEDAGOGY_MODE_OPTIONS,
  type CourseGenerationOptions,
  type CourseMaterialBindingInput,
  type CourseMaterialDraft,
  type CourseType,
  type DifficultyLevel,
  type GenerationPreflightProjection,
  type PedagogyMode,
  type PedagogyModeSelection,
} from '@/shared/prompt-config'

const props = withDefaults(defineProps<{ modelValue: boolean; busy?: boolean }>(), { busy: false })
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  generate: [payload: { subject: string; options: CourseGenerationOptions }]
  error: [message: string]
}>()

const titleId = `course-generation-title-${Math.random().toString(36).slice(2)}`
const dialogRef = ref<HTMLElement | null>(null)
const materialInputRef = ref<InstanceType<typeof MaterialInputPanel> | null>(null)
const materials = ref<CourseMaterialDraft[]>([])
const uploading = ref(false)
const submissionRequestId = ref('')
const submissionIdentity = ref('')
const preflight = ref<GenerationPreflightProjection | null>(null)
const preflightIdentity = ref('')
const busy = computed(() => props.busy || uploading.value)
const awaitingDegradedAcceptance = computed(() => (
  preflight.value?.status === 'degraded'
  && preflightIdentity.value === submissionIdentity.value
))
const preflightTitle = computed(() => ({
  ready: t('courseGeneration.preflight.readyTitle', '生成条件已就绪'),
  degraded: t('courseGeneration.preflight.degradedTitle', '可以生成，但存在风险'),
  blocked: t('courseGeneration.preflight.blockedTitle', '暂时不能开始生成'),
}[preflight.value?.status || 'ready']))
const preflightSummary = computed(() => ({
  ready: t('courseGeneration.preflight.readySummary', '模型、资料与联网能力已经完成检查。'),
  degraded: t('courseGeneration.preflight.degradedSummary', '已完成内容会保留；请确认下列风险后继续。'),
  blocked: t('courseGeneration.preflight.blockedSummary', '修复阻断项后再创建长任务，不会浪费等待时间。'),
}[preflight.value?.status || 'ready']))
const providerRouteLabel = (route?: string) => t(
  `courseGeneration.preflight.route.${route || 'none'}`,
  ({ primary: '主模型', fallback: '备用模型', none: '不可用' } as Record<string, string>)[route || 'none'] || route || '—',
)
const preflightIssueMessage = (code: string, fallback: string) => t(
  `courseGeneration.preflight.issue.${code}.message`,
  fallback,
)
const preflightIssueAction = (code: string, fallback: string) => t(
  `courseGeneration.preflight.issue.${code}.action`,
  fallback,
)
const submitLabel = computed(() => {
  if (busy.value) return t('courseGeneration.actions.submitting', '正在检查')
  if (awaitingDegradedAcceptance.value) {
    return t('courseGeneration.actions.acceptPreflight', '风险已了解，继续生成')
  }
  if (
    preflight.value?.status === 'blocked'
    && preflightIdentity.value === submissionIdentity.value
  ) {
    return t('courseGeneration.actions.retryPreflight', '重新检查生成条件')
  }
  return t('courseGeneration.actions.confirmRequirements', '确认需求，生成目录')
})
const form = reactive({
  courseType: 'systematic' as CourseType,
  systematicTopic: '',
  projectGoal: '',
  expectedDeliverable: '',
  priorExperience: '',
  currentUncertainty: '',
  coreQuestion: '',
  existingUnderstanding: '',
  evidenceScope: '',
  desiredOutput: '',
  examName: '',
  examDate: '',
  examScope: '',
  currentPreparation: '',
  difficulty: 'intermediate' as DifficultyLevel,
  pedagogyMode: 'auto' as PedagogyModeSelection,
  secondaryMode: '' as '' | PedagogyMode,
  groundingStrategy: 'material_first' as 'material_first' | 'strict_grounded' | 'general_assisted',
  assessmentGenerationProfile: 'fast' as 'fast' | 'deliberate',
  retrievalEnabled: false,
  requirements: '',
  targetAudience: '大学生',
  academicTerm: '',
  totalClassHours: 16,
  lessonDurationMinutes: 45,
  teachingContext: 'classroom' as 'classroom' | 'online' | 'blended' | 'self_study',
  classSize: undefined as number | undefined,
  classProfile: '',
  chapterCount: undefined as number | undefined,
  sectionCount: undefined as number | undefined,
})

const difficultyOptions = computed(() => ([
  { value: 'beginner' as const, tone: 'emerald', label: t('courseGeneration.difficulty.beginner.label', '入门'), detail: t('courseGeneration.difficulty.beginner.detail', '明确支架 · 标准任务') },
  { value: 'intermediate' as const, tone: 'blue', label: t('courseGeneration.difficulty.intermediate.label', '进阶'), detail: t('courseGeneration.difficulty.intermediate.detail', '独立分析 · 典型问题') },
  { value: 'advanced' as const, tone: 'violet', label: t('courseGeneration.difficulty.advanced.label', '高阶'), detail: t('courseGeneration.difficulty.advanced.detail', '开放约束 · 权衡迁移') },
]))
const courseTypeOptions = computed(() => ([
  {
    value: 'systematic' as const,
    icon: BookOpen,
    label: t('courseGeneration.courseTypes.systematic.label', '系统学习'),
    detail: t('courseGeneration.courseTypes.systematic.detail', '按知识结构和先修关系，由基础逐步进阶'),
    available: true,
  },
  {
    value: 'project' as const,
    icon: Hammer,
    label: t('courseGeneration.courseTypes.project.label', '项目实战'),
    detail: t('courseGeneration.courseTypes.project.detail', '围绕真实成果，结合个人起点边做边学'),
    available: true,
  },
  {
    value: 'inquiry' as const,
    icon: MessageCircleQuestion,
    label: t('courseGeneration.courseTypes.inquiry.label', '问题探究'),
    detail: t('courseGeneration.courseTypes.inquiry.detail', '沿子问题、证据与推理形成有依据的判断'),
    available: true,
  },
  {
    value: 'exam' as const,
    icon: Timer,
    label: t('courseGeneration.courseTypes.exam.label', '考试冲刺'),
    detail: t('courseGeneration.courseTypes.exam.detail', '根据考纲、薄弱点和剩余时间安排复习'),
    available: true,
  },
]))
const pedagogyOptions = computed(() => PEDAGOGY_MODE_OPTIONS.map(item => ({ value: item.value, label: t(item.labelKey, item.value) })))
const secondaryPedagogyOptions = computed(() => [
  { value: '' as const, label: t('courseGeneration.pedagogy.secondaryNone', '无辅助学科') },
  ...PEDAGOGY_MODE_OPTIONS
    .filter(item => item.value !== 'auto' && item.value !== form.pedagogyMode)
    .map(item => ({ value: item.value as PedagogyMode, label: t(item.labelKey, item.value) })),
])
const todayIso = new Date().toLocaleDateString('en-CA')
const activeSubject = computed(() => ({
  systematic: form.systematicTopic,
  project: form.projectGoal,
  inquiry: form.coreQuestion,
  exam: form.examName,
}[form.courseType].trim()))
const typeIntentComplete = computed(() => ({
  systematic: Boolean(form.systematicTopic.trim()),
  project: Boolean(form.projectGoal.trim() && form.expectedDeliverable.trim()),
  inquiry: Boolean(form.coreQuestion.trim() && form.desiredOutput.trim()),
  exam: Boolean(form.examName.trim() && form.examDate.trim() && form.examScope.trim()),
}[form.courseType]))
const hasStartingPointInput = computed(() => Boolean(form.priorExperience.trim() || form.currentUncertainty.trim()))
const canSubmit = computed(() => !busy.value && typeIntentComplete.value && Boolean(form.targetAudience.trim())
  && Number.isInteger(form.totalClassHours) && form.totalClassHours >= 1 && form.totalClassHours <= 1000
  && Number.isInteger(form.lessonDurationMinutes) && form.lessonDurationMinutes >= 20 && form.lessonDurationMinutes <= 240
  && (!form.chapterCount || !form.sectionCount || form.sectionCount >= form.chapterCount)
)
watch(() => props.modelValue, async open => {
  if (!open) {
    submissionRequestId.value = ''
    submissionIdentity.value = ''
    preflight.value = null
    preflightIdentity.value = ''
    return
  }
  await nextTick()
  dialogRef.value?.focus()
})

watch(() => form.pedagogyMode, primaryMode => {
  if (primaryMode !== 'auto' && form.secondaryMode === primaryMode) form.secondaryMode = ''
})

function close() {
  if (!busy.value) emit('update:modelValue', false)
}

function selectCourseType(courseType: CourseType) {
  const option = courseTypeOptions.value.find(item => item.value === courseType)
  if (!busy.value && option?.available) form.courseType = courseType
}

function emitGeneration(
  subject: string,
  options: CourseGenerationOptions,
  acceptance?: GenerationPreflightProjection,
) {
  emit('generate', {
    subject,
    options: {
      ...options,
      request_id: submissionRequestId.value,
      ...(acceptance
        ? {
            preflight_acceptance: {
              preflight_id: acceptance.preflight_id,
              accepted_issue_codes: acceptance.issues.map(item => item.code),
            },
          }
        : {}),
    },
  })
}

async function submit() {
  const subject = activeSubject.value
  if (!canSubmit.value) return
  uploading.value = true
  try {
    const materialBindings: CourseMaterialBindingInput[] = materials.value.length
      ? (await materialInputRef.value?.ensureUploaded()) ?? []
      : []
    const options: CourseGenerationOptions = {
      difficulty: form.difficulty,
      composition_style: ({
        systematic: 'balanced',
        project: 'project_driven',
        inquiry: 'inquiry_driven',
        exam: 'example_driven',
      } as const)[form.courseType],
      pedagogy_mode: form.pedagogyMode,
      ...(form.secondaryMode
        ? { secondary_mode: form.secondaryMode, secondary_intensity: 'collaborative' as const }
        : {}),
      generation_mode: 'review_blueprint',
      assessment_generation_profile: form.assessmentGenerationProfile,
      course_purpose: form.courseType === 'exam' ? 'exam_sprint' : 'systematic',
      course_type: form.courseType,
      course_intent: form.courseType === 'project'
        ? {
            schema_version: 'course_intent_v1',
            type: 'project',
            project_goal: form.projectGoal.trim(),
            expected_deliverable: form.expectedDeliverable.trim(),
            prior_experience: form.priorExperience.trim(),
            current_uncertainty: form.currentUncertainty.trim(),
            project_constraints: form.requirements.trim(),
          }
        : form.courseType === 'inquiry'
          ? {
              schema_version: 'course_intent_v1',
              type: 'inquiry',
              core_question: form.coreQuestion.trim(),
              existing_understanding: form.existingUnderstanding.trim(),
              evidence_scope: form.evidenceScope.trim(),
              desired_output: form.desiredOutput.trim(),
            }
          : form.courseType === 'exam'
            ? {
                schema_version: 'course_intent_v1',
                type: 'exam',
                exam_name: form.examName.trim(),
                exam_date: form.examDate,
                exam_scope: form.examScope.trim(),
                current_preparation: form.currentPreparation.trim(),
              }
            : {
                schema_version: 'course_intent_v1',
                type: 'systematic',
                learning_goal: subject,
                desired_outcome: form.requirements.trim(),
              },
      grounding_strategy: form.groundingStrategy,
      requirements: form.requirements.trim(),
      material_bindings: materialBindings || [],
      target_audience: form.targetAudience.trim(),
      teacher_course_brief: {
        schema_version: 'teacher_course_brief_v1',
        academic_term: form.academicTerm.trim(),
        target_audience: form.targetAudience.trim(),
        total_class_hours: form.totalClassHours,
        lesson_duration_minutes: form.lessonDurationMinutes,
        teaching_context: form.teachingContext,
        ...(form.classSize ? { class_size: form.classSize } : {}),
        ...(form.classProfile.trim() ? { class_profile: form.classProfile.trim() } : {}),
        ...(form.chapterCount ? { chapter_count: form.chapterCount } : {}),
        ...(form.sectionCount ? { section_count: form.sectionCount } : {}),
        additional_requirements: form.requirements.trim(),
        material_refs: (materialBindings || []).map(binding => ({
          resource_id: binding.asset_id,
          label: binding.source_label || binding.asset_id,
          parse_status: 'ready',
        })),
      },
      retrieval: { enabled: form.retrievalEnabled },
    }
    const identity = JSON.stringify({ subject, options })
    if (!submissionRequestId.value || submissionIdentity.value !== identity) {
      submissionRequestId.value = crypto.randomUUID()
      submissionIdentity.value = identity
      preflight.value = null
      preflightIdentity.value = ''
    }
    if (
      preflight.value?.status === 'degraded'
      && preflightIdentity.value === identity
    ) {
      emitGeneration(subject, options, preflight.value)
      return
    }
    const response = await http.post('/api/course-generation/preflight', {
      subject,
      ...options,
      request_id: submissionRequestId.value,
    })
    preflight.value = response.data as GenerationPreflightProjection
    preflightIdentity.value = identity
    if (preflight.value.status === 'ready') {
      emitGeneration(subject, options)
    }
  } catch (error: any) {
    emit('error', error?.response?.data?.detail?.message || error?.message || t('courseGeneration.preflight.failed', '生成条件检查失败，请稍后重试'))
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.generation-dialog-layer { position: fixed; inset: 0; z-index: 520; display: grid; place-items: center; padding: 20px; }
.generation-dialog-backdrop { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; background: rgba(30, 41, 59, .34); backdrop-filter: blur(5px); cursor: default; }
.generation-dialog { position: relative; width: min(920px, 100%); max-height: min(860px, calc(100vh - 40px)); display: grid; grid-template-rows: auto minmax(0, 1fr) auto; overflow: clip; border: 1px solid rgba(255,255,255,.92); border-radius: var(--lz-radius-surface); color: var(--lz-text); background: rgba(255,255,255,.98); box-shadow: var(--lz-shadow-overlay); outline: none; }
.generation-dialog__header { min-height: 68px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 0 18px 0 22px; border-bottom: 1px solid var(--lz-border); }
.generation-dialog__heading { min-width: 0; display: flex; align-items: center; gap: 11px; }
.generation-dialog__mark { width: 36px; height: 36px; flex: 0 0 auto; display: grid; place-items: center; border-radius: 10px; color: var(--lz-brand-strong); background: var(--lz-brand-soft); }
.generation-dialog__heading p { margin: 0 0 2px; color: var(--lz-text-muted); font-size: 10px; font-weight: 700; }
.generation-dialog__heading h2 { margin: 0; color: var(--lz-text-strong); font-size: 17px; line-height: 1.25; }
.icon-button { width: 34px; height: 34px; display: grid; place-items: center; border: 0; border-radius: 7px; color: var(--lz-text-secondary); background: transparent; cursor: pointer; }
.icon-button:hover { color: var(--lz-text-strong); background: var(--lz-surface-muted); }
.generation-dialog__body { min-height: 0; overflow: auto; padding: 4px 24px 24px; }
.form-section { padding: 20px 0; border-bottom: 1px solid rgba(226,232,240,.78); }
.form-section:last-child { border-bottom: 0; }
.form-section--lead { padding-top: 22px; }
.course-type-section { padding-bottom: 18px; }
.course-type-options { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; }
.course-type-option { position: relative; min-width: 0; min-height: 74px; display: grid; grid-template-columns: 30px minmax(0, 1fr) 17px; align-items: start; gap: 9px; padding: 11px 10px; border: 1px solid rgba(226,232,240,.92); border-radius: 10px; color: var(--lz-text-secondary); background: #fff; text-align: left; cursor: pointer; transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease, background .16s ease; }
.course-type-option:hover:not(:disabled) { transform: translateY(-1px); border-color: rgba(165,180,252,.72); box-shadow: 0 7px 16px rgba(79,70,229,.07); }
.course-type-option.active { border-color: var(--lz-brand); color: var(--lz-brand-strong); background: rgba(238,242,255,.72); box-shadow: inset 0 0 0 1px rgba(99,102,241,.08); }
.course-type-option:focus-visible { outline: 2px solid var(--lz-brand); outline-offset: 2px; }
.course-type-option:disabled { cursor: not-allowed; color: var(--lz-text-muted); background: var(--lz-surface-muted); opacity: .72; }
.course-type-option__icon { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 8px; color: var(--lz-brand); background: var(--lz-brand-soft); }
.course-type-option:disabled .course-type-option__icon { color: var(--lz-text-muted); background: #fff; }
.course-type-option__copy { min-width: 0; display: grid; gap: 5px; }
.course-type-option__copy > span:last-child { overflow-wrap: anywhere; color: var(--lz-text-muted); font-size: 11px; line-height: 1.45; }
.course-type-option__heading { min-width: 0; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; }
.course-type-option__heading strong { color: inherit; font-size: 13px; }
.course-type-option__heading small { padding: 2px 5px; border-radius: 4px; color: var(--lz-text-muted); background: #fff; font-size: 8px; font-weight: 650; }
.course-type-option__check { width: 17px; height: 17px; display: grid; place-items: center; border: 1px solid var(--lz-border); border-radius: 50%; color: transparent; background: var(--lz-surface-muted); }
.course-type-option.active .course-type-option__check { border-color: var(--lz-brand); color: #fff; background: var(--lz-brand); }
.intent-section { padding-top: 18px; }
.project-intent { display: grid; gap: 16px; }
.project-intent__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; color: var(--lz-brand-strong); }
.project-intent__heading > div { min-width: 0; display: grid; gap: 4px; }
.project-intent__heading strong { color: var(--lz-text-strong); font-size: 13px; }
.project-intent__heading span { color: var(--lz-text-muted); font-size: 10px; line-height: 1.5; }
.project-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.project-field { min-width: 0; }
.project-field--wide { grid-column: 1 / -1; }
.textarea-input--compact { min-height: 72px; }
.starting-point-note { margin: 0; display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; border: 1px solid rgba(99,102,241,.18); border-radius: 8px; color: var(--lz-text-secondary); background: rgba(238,242,255,.58); font-size: 10px; line-height: 1.55; }
.starting-point-note svg { flex: 0 0 auto; margin-top: 1px; color: var(--lz-brand-strong); }
.starting-point-note strong { display: block; margin-bottom: 1px; color: var(--lz-text-strong); font-size: 10px; }
.web-enrichment-setting__control { display: flex; align-items: flex-start; gap: 11px; cursor: pointer; }
.web-enrichment-setting__control input { margin-top: 3px; accent-color: var(--lz-brand-strong); }
.web-enrichment-setting__control span { display: grid; gap: 4px; }
.web-enrichment-setting__control strong { color: var(--lz-text-strong); font-size: 13px; }
.web-enrichment-setting__control small { color: var(--lz-text-muted); font-size: 11px; line-height: 1.55; }
.course-basis-section { display:grid; gap:14px; }
.course-basis-section__heading { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; color:var(--lz-brand-strong); }
.course-basis-section__heading > div { min-width:0; display:grid; gap:4px; }
.course-basis-section__heading strong { color:var(--lz-text-strong); font-size:14px; }
.course-basis-section__heading span { color:var(--lz-text-muted); font-size:12px; line-height:1.55; }
.course-basis-section__web { padding:12px 14px; border:1px solid rgba(99,102,241,.18); border-radius:10px; background:rgba(238,242,255,.46); }
.course-basis-section .material-section { padding-top:2px; }
.generation-advanced-settings { padding:0; }
.generation-advanced-settings > summary { display:flex; align-items:center; justify-content:space-between; gap:18px; padding:18px 0; color:var(--lz-text-secondary); cursor:pointer; list-style:none; }
.generation-advanced-settings > summary::-webkit-details-marker { display:none; }
.generation-advanced-settings > summary > span:first-child { display:grid; gap:3px; }
.generation-advanced-settings > summary strong { color:var(--lz-text-strong); font-size:14px; }
.generation-advanced-settings > summary small { color:var(--lz-text-muted); font-size:12px; line-height:1.5; }
.generation-advanced-settings > summary > span:last-child { padding:3px 8px; border-radius:999px; color:var(--lz-brand-strong); background:var(--lz-brand-soft); font-size:11px; font-weight:750; }
.generation-advanced-settings[open] > summary { border-bottom:1px solid rgba(226,232,240,.78); }
.generation-advanced-settings__body { display:grid; gap:22px; padding:22px 0; }
.generation-advanced-settings__body > section + section { padding-top:20px; border-top:1px solid rgba(226,232,240,.78); }
.teaching-settings { display: grid; gap: 22px; }
.teaching-settings__core { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 32px; }
.teaching-settings__core--common { align-items: start; }
.teaching-settings__core--common .strategy-settings { padding-top: 0; border-top: 0; }
.choice-group { min-width: 0; margin: 0; padding: 0; border: 0; }
.choice-group__title { width: 100%; display: flex; align-items: center; gap: 8px; margin: 0 0 11px; padding: 0; color: var(--lz-text); font-size: 12px; font-weight: 750; }
.choice-group__title > span:last-child { display:grid; gap:2px; }
.choice-group__title small { color:var(--lz-text-muted); font-size:9px; font-weight:500; line-height:1.35; }
.field-icon { width: 25px; height: 25px; display: grid; place-items: center; border: 1px solid; border-radius: 8px; box-shadow: 0 2px 7px rgba(15,23,42,.04); }
.field-icon--amber { border-color: #fde7b0; color: #d97706; background: #fffbeb; }
.field-icon--rose { border-color: #fbcfe8; color: #db2777; background: #fdf2f8; }
.difficulty-options { display: grid; gap: 9px; }
.difficulty-option { --choice-accent: #60a5fa; min-width: 0; min-height: 58px; display: grid; grid-template-columns: 5px minmax(0, 1fr) 20px; align-items: center; gap: 11px; padding: 9px 11px; border: 1px solid rgba(226,232,240,.92); border-radius: 12px; color: var(--lz-text-secondary); background: #fff; text-align: left; box-shadow: 0 2px 8px rgba(15,23,42,.025); cursor: pointer; transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease, background .16s ease; }
.difficulty-option[data-tone="emerald"] { --choice-accent: #34d399; }
.difficulty-option[data-tone="blue"] { --choice-accent: #60a5fa; }
.difficulty-option[data-tone="violet"] { --choice-accent: #a78bfa; }
.difficulty-option:hover:not(:disabled) { transform: translateY(-1px); border-color: rgba(165,180,252,.72); box-shadow: 0 7px 16px rgba(79,70,229,.07); }
.difficulty-option.active { border-color: var(--lz-brand); background: linear-gradient(135deg,#fff,rgba(238,242,255,.72)); box-shadow: 0 8px 18px rgba(79,70,229,.09), inset 0 0 0 1px rgba(99,102,241,.08); }
.difficulty-option__rail { width: 5px; height: 34px; border-radius: 4px; background: #e2e8f0; transition: background .16s ease; }
.difficulty-option.active .difficulty-option__rail { background: var(--choice-accent); }
.difficulty-option__copy { min-width: 0; display: block; }
.difficulty-option__copy strong { display: block; color: var(--lz-text); font-size: 12px; }
.difficulty-option__copy small { display: block; margin-top: 2px; overflow: hidden; color: var(--lz-text-muted); font-size: 10px; line-height: 1.35; text-overflow: ellipsis; white-space: nowrap; }
.difficulty-option__check { display: grid; place-items: center; border: 1px solid var(--lz-border); border-radius: 50%; color: transparent; background: var(--lz-surface-muted); transition: color .16s ease, border-color .16s ease, background .16s ease, transform .16s ease; }
.difficulty-option__check { width: 20px; height: 20px; }
.difficulty-option.active .difficulty-option__check { border-color: var(--lz-brand); color: #fff; background: var(--lz-brand); transform: scale(1.06); }
.difficulty-option:disabled { cursor: not-allowed; opacity: .6; }
.strategy-settings { padding-top: 18px; border-top: 1px dashed rgba(203,213,225,.72); }
.strategy-settings__heading { display: flex; align-items: baseline; gap: 9px; margin-bottom: 11px; }
.strategy-settings__heading strong { color: var(--lz-text); font-size: 12px; }
.strategy-settings__heading span { color: var(--lz-text-muted); font-size: 10px; }
.teacher-brief-section { display:grid; gap:14px; }
.teacher-brief-section__heading { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; color:var(--lz-brand-strong); }
.teacher-brief-section__heading > div { min-width:0; display:grid; gap:4px; }
.teacher-brief-section__heading strong { color:var(--lz-text); font-size:13px; }
.teacher-brief-section__heading span { color:var(--lz-text-muted); font-size:10px; line-height:1.5; }
.teacher-brief-section__core,.teacher-brief-section__advanced-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.teacher-brief-section__advanced { min-width:0; padding-top:12px; border-top:1px solid rgba(226,232,240,.78); }
.teacher-brief-section__advanced summary { color:var(--lz-text-secondary); font-size:12px; font-weight:700; cursor:pointer; }
.teacher-brief-section__advanced[open] summary { margin-bottom:14px; color:var(--lz-brand-strong); }
.teacher-brief-section__advanced-body { display:grid; gap:12px; }
.teacher-brief-section__profile { display:grid; gap:0; }
.compact-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }
.field-label { display: block; margin-bottom: 8px; color: var(--lz-text); font-size: 13px; font-weight: 700; }
.compact-grid .field-label { display: flex; align-items: center; gap: 6px; color: var(--lz-text-secondary); font-size: 10px; }
.text-input,.select-input,.textarea-input { width: 100%; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text-strong); background: #fff; outline: none; transition: border-color .16s ease, box-shadow .16s ease; }
.text-input:focus,.select-input:focus,.textarea-input:focus { border-color: var(--lz-brand); box-shadow: 0 0 0 3px rgba(99,102,241,.1); }
.text-input:disabled,.select-input:disabled,.textarea-input:disabled { cursor: not-allowed; opacity: .6; }
.text-input { height: 42px; padding: 0 12px; }
.text-input--large { height: 48px; font-size: 15px; }
.select-input { height: 38px; padding: 0 9px; font-size: 12px; }
.textarea-input { min-height: 82px; padding: 10px 12px; resize: vertical; line-height: 1.6; font-size: 12px; }
.field-help { margin: 7px 0 0; color: var(--lz-text-muted); font-size: 11px; line-height: 1.5; }
.segmented-options { display: grid; gap: 8px; }
.segmented-options--three { grid-template-columns: repeat(3, 1fr); }
.segmented-options--two { grid-template-columns: repeat(2, 1fr); }
.segmented-options button { min-width: 0; min-height: 66px; display: flex; align-items: center; justify-content: flex-start; gap: 10px; padding: 10px 12px; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text-secondary); background: #fff; text-align: left; cursor: pointer; }
.segmented-options button:hover { border-color: rgba(99,102,241,.46); }
.segmented-options button.active { border-color: var(--lz-brand); color: var(--lz-brand-strong); background: var(--lz-brand-soft); box-shadow: inset 0 0 0 1px rgba(99,102,241,.1); }
.segmented-options button:disabled { cursor: not-allowed; opacity: .6; }
.segmented-options strong { display: block; color: inherit; font-size: 12px; }
.segmented-options span { min-width: 0; display: block; color: var(--lz-text-muted); font-size: 10px; line-height: 1.45; }
.segmented-options span strong { margin-bottom: 2px; }
.material-section :deep(section) { margin: 0; }
.generation-dialog__footer { min-height: 64px; display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 10px 18px 10px 24px; border-top: 1px solid var(--lz-border); background: rgba(248,250,252,.84); }
.generation-preflight { display:grid; gap:10px; margin:18px 0 4px; padding:13px 14px; border:1px solid #bbf7d0; border-radius:12px; background:#f0fdf4; }
.generation-preflight--degraded { border-color:#fde68a; background:#fffbeb; }
.generation-preflight--blocked { border-color:#fecaca; background:#fef2f2; }
.generation-preflight__summary { display:grid; grid-template-columns:30px minmax(0,1fr) auto; align-items:center; gap:10px; }
.generation-preflight__icon { width:30px; height:30px; display:grid; place-items:center; border-radius:9px; color:#047857; background:#dcfce7; }
.generation-preflight--degraded .generation-preflight__icon { color:#b45309; background:#fef3c7; }
.generation-preflight--blocked .generation-preflight__icon { color:#b91c1c; background:#fee2e2; }
.generation-preflight__summary strong,.generation-preflight__summary span { display:block; }
.generation-preflight__summary strong { color:var(--lz-text-strong); font-size:12px; }
.generation-preflight__summary span { margin-top:2px; color:var(--lz-text-secondary); font-size:10px; line-height:1.45; }
.generation-preflight__summary small { padding:3px 7px; border-radius:999px; color:var(--lz-text-secondary); background:rgba(255,255,255,.72); font-size:9px; font-weight:750; }
.generation-preflight__facts { display:flex; flex-wrap:wrap; gap:6px; }
.generation-preflight__facts span { padding:4px 7px; border:1px solid rgba(148,163,184,.2); border-radius:7px; color:var(--lz-text-secondary); background:rgba(255,255,255,.72); font-size:9px; }
.generation-preflight__issues { display:grid; gap:7px; margin:0; padding:0; list-style:none; }
.generation-preflight__issues li { display:grid; gap:2px; padding-top:7px; border-top:1px solid rgba(148,163,184,.2); }
.generation-preflight__issues strong { color:var(--lz-text); font-size:10px; }
.generation-preflight__issues span { color:var(--lz-text-muted); font-size:9px; line-height:1.45; }
.generation-dialog__footer > div:first-child { min-width: 0; display: flex; align-items: center; gap: 7px; color: var(--lz-text-muted); font-size: 10px; }
.footer-actions { display: flex; gap: 8px; flex: 0 0 auto; }
.primary-button,.secondary-button { min-height: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 0 15px; border-radius: 8px; font-size: 12px; font-weight: 700; cursor: pointer; }
.primary-button { border: 1px solid var(--lz-brand-strong); color: #fff; background: var(--lz-brand-strong); }
.secondary-button { border: 1px solid var(--lz-border); color: var(--lz-text-secondary); background: #fff; }
.primary-button:disabled,.secondary-button:disabled { cursor: not-allowed; opacity: .55; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 760px) {
  .generation-dialog-layer { align-items: end; padding: 0; }
  .generation-dialog { width: 100%; max-height: calc(100vh - 56px); border-radius: 14px 14px 0 0; }
  .generation-dialog__body { padding-inline: 16px; }
  .teaching-settings__core { grid-template-columns: 1fr; gap: 22px; }
  .course-type-options { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .compact-grid { grid-template-columns: 1fr 1fr; }
  .teacher-brief-section__core,.teacher-brief-section__advanced-grid { grid-template-columns:1fr; }
  .generation-dialog__footer { align-items: stretch; flex-direction: column; padding: 10px 16px 14px; }
  .footer-actions,.footer-actions button { width: 100%; }
  .footer-actions button { flex: 1; }
}
@media (max-width: 520px) {
  .segmented-options--three,.segmented-options--two,.compact-grid { grid-template-columns: 1fr; }
  .course-type-options,.project-fields { grid-template-columns: 1fr; }
  .project-field--wide { grid-column: auto; }
  .segmented-options button { min-height: 52px; }
  .strategy-settings__heading { align-items: flex-start; flex-direction: column; gap: 3px; }
}
</style>
