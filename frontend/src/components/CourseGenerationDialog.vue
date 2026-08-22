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
        :class="{ 'generation-dialog--course-space': props.courseSpaceMode }"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
      >
        <header class="generation-dialog__header">
          <span v-if="props.courseSpaceMode" class="generation-dialog__brand" aria-hidden="true">
            <Sparkles :size="24" />
          </span>
          <div class="generation-dialog__heading">
            <h2 :id="titleId">{{ props.title || (props.workbenchMode ? t('courseFiles.workbench.settingsDialogTitle') : props.initialSubject ? t('courseGeneration.dialog.createOutline', '生成课程大纲') : t('teacherHome.newCourse', '新建课程')) }}</h2>
            <p v-if="!props.courseSpaceMode && (props.helpText || props.workbenchMode)">{{ props.helpText || t('courseFiles.workbench.settingsDialogHelp') }}</p>
          </div>
          <button type="button" class="icon-button" :title="t('common.cancel', '取消')" @click="close">
            <X :size="18" />
          </button>
        </header>

        <form class="generation-dialog__body" @submit.prevent="submit">
          <section v-if="!props.initialSubject || props.showCourseType" class="form-section form-section--lead course-type-section">
            <fieldset class="choice-group">
              <legend class="choice-group__title">
                <span class="field-icon field-icon--rose"><Route :size="14" /></span>
                <span>{{ t('courseGeneration.courseTypes.label', '课程类型') }}</span>
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
                  :aria-label="`${item.label}：${item.detail}`"
                  :title="item.detail"
                  :disabled="busy || !item.available"
                  @click="selectCourseType(item.value)"
                >
                  <span class="course-type-option__icon"><component :is="item.icon" :size="18" /></span>
                  <span class="course-type-option__copy">
                    <span class="course-type-option__heading">
                      <strong>{{ item.label }}</strong>
                    </span>
                  </span>
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
          </section>

          <section v-else-if="form.courseType === 'project'" class="form-section intent-section project-intent" data-testid="project-intent-form">
            <div class="project-intent__heading">
              <div>
                <strong>{{ t('courseGeneration.project.title', '定义你的实战项目') }}</strong>
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
              <label v-if="!props.courseSpaceMode" class="project-field" for="project-prior-experience">
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
              <label v-if="!props.courseSpaceMode" class="project-field" for="project-current-uncertainty">
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
          </section>

          <section v-else-if="form.courseType === 'inquiry'" class="form-section intent-section project-intent" data-testid="inquiry-intent-form">
            <div class="project-intent__heading">
              <div>
                <strong>{{ t('courseGeneration.inquiry.title', '定义要探究的问题') }}</strong>
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
              <label v-if="!props.courseSpaceMode" class="project-field" for="inquiry-understanding">
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
              <label v-if="!props.courseSpaceMode" class="project-field" for="inquiry-evidence-scope">
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
          </section>

          <section v-else class="form-section intent-section project-intent" data-testid="exam-intent-form">
            <div class="project-intent__heading">
              <div>
                <strong>{{ t('courseGeneration.exam.title', '定义你的冲刺目标') }}</strong>
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
              <label v-if="!props.courseSpaceMode" class="project-field project-field--wide" for="exam-preparation">
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
          </section>

          <section v-if="props.courseSpaceMode" class="form-section course-goal-section">
            <label class="field-label" for="course-learning-goal">{{ t('teacherCourseCreate.goal', '课程目标') }}</label>
            <textarea
              id="course-learning-goal"
              v-model="form.requirements"
              class="textarea-input"
              maxlength="3000"
              :placeholder="t('teacherCourseCreate.goalPlaceholder', '学生完成课程后能够……')"
              :disabled="busy"
            />
          </section>

          <section class="form-section teacher-brief-section" data-testid="teacher-course-brief-form">
            <div class="teacher-brief-section__heading">
              <strong>{{ props.courseSpaceMode ? t('teacherCourseCreate.courseScale', '课程规模') : (activeLocale === 'en' ? 'Teaching setup' : '授课信息') }}</strong>
            </div>
            <div class="teacher-brief-section__core">
              <label v-if="!props.courseSpaceMode && !props.fixedAudience" for="teacher-target-audience">
                <span class="field-label">{{ t('courseGeneration.teacherBrief.targetAudience', '教学对象') }}</span>
                <input id="teacher-target-audience" v-model="form.targetAudience" class="text-input" type="text" maxlength="500" :disabled="busy" />
              </label>
              <div v-else-if="!props.courseSpaceMode" class="fixed-audience-field">
                <span class="field-label">{{ t('courseGeneration.teacherBrief.targetAudience', '教学对象') }}</span>
                <strong>{{ props.fixedAudience }}</strong>
              </div>
              <label v-if="props.courseSpaceMode" for="teacher-academic-term">
                <span class="field-label">{{ t('courseGeneration.teacherBrief.academicTerm', '开课学期') }}</span>
                <input id="teacher-academic-term" v-model="form.academicTerm" class="text-input" type="text" maxlength="100" :placeholder="t('courseGeneration.teacherBrief.academicTermPlaceholder', '2026-2027 第一学期')" :disabled="busy" />
              </label>
              <label for="teacher-total-hours">
                <span class="field-label">{{ t('courseGeneration.teacherBrief.totalHours', '总课时') }}</span>
                <input id="teacher-total-hours" v-model.number="form.totalClassHours" class="text-input" type="number" min="1" max="1000" step="1" :disabled="busy" />
              </label>
              <label v-if="props.courseSpaceMode" for="teacher-section-count">
                <span class="field-label">{{ t('teacherCourseCreate.expectedSessions', '预计课次') }}</span>
                <input id="teacher-section-count" v-model.number="form.sectionCount" class="text-input" type="number" min="1" max="500" step="1" :disabled="busy" />
              </label>
            </div>
            <details v-if="!props.courseSpaceMode" class="teacher-brief-section__advanced">
              <summary>{{ t('courseGeneration.teacherBrief.advancedSettings', '更多课堂设置') }}</summary>
              <div class="teacher-brief-section__advanced-body">
                <div class="teacher-brief-section__advanced-grid">
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

          <details class="form-section teaching-settings generation-advanced" :open="props.courseSpaceMode">
            <summary>{{ props.courseSpaceMode ? t('teacherCourseCreate.depthAndStructure', '内容深度与知识组织') : (activeLocale === 'en' ? 'More generation settings' : '更多生成设置') }}</summary>
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
                  :aria-label="`${item.label}：${item.detail}`"
                  :title="item.detail"
                  :disabled="busy"
                  @click="form.difficulty = item.value"
                >
                  <span class="difficulty-option__copy">
                    <strong>{{ item.label }}</strong>
                  </span>
                </button>
                </div>
              </fieldset>

              <div class="strategy-settings">
              <div class="strategy-settings__heading">
                <strong>{{ t('courseFiles.workbench.knowledgeStructure', '知识结构') }}</strong>
              </div>
              <div class="compact-grid" :class="{ 'compact-grid--course-space': props.courseSpaceMode }">
              <label>
                <span class="field-label"><Route :size="13" />{{ t('courseGeneration.pedagogy.label', '主学科结构') }}</span>
                <select v-model="form.pedagogyMode" class="select-input" :disabled="busy">
                  <option v-for="item in pedagogyOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
                </select>
              </label>
              <label v-if="!props.courseSpaceMode">
                <span class="field-label"><Network :size="13" />{{ t('courseGeneration.pedagogy.secondaryLabel', '辅助学科') }}</span>
                <select v-model="form.secondaryMode" data-testid="secondary-pedagogy-mode" class="select-input" :disabled="busy">
                  <option v-for="item in secondaryPedagogyOptions" :key="item.value || 'none'" :value="item.value">{{ item.label }}</option>
                </select>
              </label>
              <label v-if="!props.courseSpaceMode">
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
          </details>

          <section v-if="props.courseSpaceMode" class="form-section production-mode-section">
            <fieldset class="choice-group">
              <legend class="choice-group__title">
                <span class="field-icon field-icon--rose"><Sparkles :size="14" /></span>
                {{ t('teacherCourseCreate.productionMode', '生产模式') }}
              </legend>
              <div class="production-mode-options">
                <button type="button" :class="{ active: form.productionMode === 'manual' }" :aria-pressed="form.productionMode === 'manual'" :disabled="busy" @click="form.productionMode = 'manual'">
                  <strong>{{ t('teacherCourseCreate.productionModeManual', '分步确认') }}</strong>
                  <small>{{ t('teacherCourseCreate.productionModeManualHelp') }}</small>
                </button>
                <button type="button" :class="{ active: form.productionMode === 'automatic' }" :aria-pressed="form.productionMode === 'automatic'" :disabled="busy" @click="form.productionMode = 'automatic'">
                  <strong>{{ t('teacherCourseCreate.productionModeAutomatic', '自动衔接') }}</strong>
                  <small>{{ t('teacherCourseCreate.productionModeAutomaticHelp') }}</small>
                </button>
              </div>
            </fieldset>
          </section>

          <details v-if="!props.courseSpaceMode" class="form-section supplemental-settings">
            <summary>{{ activeLocale === 'en' ? 'Research and additional requirements' : '联网与补充要求' }}</summary>
            <div class="supplemental-settings__body">
              <section class="web-enrichment-setting">
                <label class="web-enrichment-setting__control">
                  <input
                    v-model="form.generateQuestions"
                    data-testid="generate-course-questions"
                    type="checkbox"
                    :disabled="busy"
                  />
                  <span>
                    <strong>{{ t('courseGeneration.questions.generateWithCourse', '同时生成题目') }}</strong>
                    <small>{{ t('courseGeneration.questions.generateWithCourseHelp', '默认关闭。课程发布后仍可随时从学生端“题库本”按小节或全课程生成。') }}</small>
                  </span>
                </label>
              </section>
          <section class="web-enrichment-setting">
            <label class="web-enrichment-setting__control">
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
          </section>

          <section v-if="form.retrievalEnabled" class="web-enrichment-setting">
            <label class="web-enrichment-setting__control">
              <input
                v-model="form.webMaterialIngest"
                data-testid="web-material-ingest"
                type="checkbox"
                :disabled="busy"
              />
              <span>
                <strong>{{ t('courseGeneration.materials.webSearch.ingestLabel', '把联网资料并入课程资料库') }}</strong>
                <small>{{ t('courseGeneration.materials.webSearch.ingestHint', '联网结果会与导入资料同路解析并保留出处；关闭则只作为本次生成的引用，不落库。') }}</small>
              </span>
            </label>
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

          <section v-if="!props.courseSpaceMode" class="form-section material-section">
            <MaterialInputPanel ref="materialInputRef" v-model="materials" :disabled="busy" />
          </section>
        </form>

        <footer class="generation-dialog__footer">
          <div class="footer-actions">
            <button type="button" class="secondary-button" :disabled="busy" @click="close">
              {{ t('common.cancel', '取消') }}
            </button>
            <button type="button" class="primary-button" :disabled="!canSubmit" @click="submit">
              <LoaderCircle v-if="busy" class="spin" :size="16" />
              <Sparkles v-else :size="16" />
              {{ busy ? t('courseGeneration.actions.submitting', '正在提交') : props.submitLabel || (props.workbenchMode ? t('courseFiles.workbench.applySettings') : t('courseGeneration.actions.confirmRequirements', '确认需求，生成目录')) }}
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
  Hammer,
  LoaderCircle,
  MessageCircleQuestion,
  Network,
  Route,
  Sparkles,
  Target,
  Timer,
  Trophy,
  X,
} from 'lucide-vue-next'
import MaterialInputPanel from './MaterialInputPanel.vue'
import { activeLocale, t } from '@/shared/i18n'
import {
  PEDAGOGY_MODE_OPTIONS,
  type CourseGenerationOptions,
  type CourseMaterialDraft,
  type CourseType,
  type DifficultyLevel,
  type PedagogyMode,
  type PedagogyModeSelection,
} from '@/shared/prompt-config'

const props = withDefaults(defineProps<{
  modelValue: boolean
  busy?: boolean
  initialSubject?: string
  initialAudience?: string
  initialAcademicTerm?: string
  initialTotalClassHours?: number
  initialLessonDurationMinutes?: number
  initialChapterCount?: number
  initialSectionCount?: number
  initialOptions?: CourseGenerationOptions
  initialContextKey?: string
  workbenchMode?: boolean
  showCourseType?: boolean
  title?: string
  helpText?: string
  submitLabel?: string
  courseSpaceMode?: boolean
  fixedAudience?: string
}>(), {
  busy: false,
  initialSubject: '',
  initialAudience: '',
  initialAcademicTerm: '',
  initialTotalClassHours: undefined,
  initialLessonDurationMinutes: undefined,
  initialChapterCount: undefined,
  workbenchMode: false,
  showCourseType: false,
  title: '',
  helpText: '',
  submitLabel: '',
  courseSpaceMode: false,
  fixedAudience: '',
})
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
const busy = computed(() => props.busy || uploading.value)
const defaultAudience = () => t(
  'courseGeneration.teacherBrief.defaultAudience',
  activeLocale.value === 'en' ? 'University students' : '大学生',
)
let lastDefaultAudience = defaultAudience()
let lastOpenContextKey = ''
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
  retrievalEnabled: false,
  generateQuestions: false,
  webMaterialIngest: true,
  requirements: '',
  targetAudience: lastDefaultAudience,
  academicTerm: '',
  totalClassHours: 16,
  lessonDurationMinutes: 45,
  teachingContext: 'classroom' as 'classroom' | 'online' | 'blended' | 'self_study',
  classSize: undefined as number | undefined,
  classProfile: '',
  chapterCount: undefined as number | undefined,
  sectionCount: undefined as number | undefined,
  productionMode: 'manual' as 'manual' | 'automatic',
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

function resetFormForOpen() {
  lastDefaultAudience = defaultAudience()
  Object.assign(form, {
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
    groundingStrategy: 'material_first' as const,
    retrievalEnabled: false,
    generateQuestions: false,
    webMaterialIngest: true,
    requirements: '',
    targetAudience: lastDefaultAudience,
    academicTerm: '',
    totalClassHours: 16,
    lessonDurationMinutes: 45,
    teachingContext: 'classroom' as const,
    classSize: undefined,
    classProfile: '',
    chapterCount: undefined,
    sectionCount: undefined,
    productionMode: 'manual' as const,
  })
}

function hydrateInitialOptions(options?: CourseGenerationOptions) {
  if (!options) return
  const brief = options.teacher_course_brief
  const intent = options.course_intent as Record<string, any> | undefined
  if (['systematic', 'project', 'inquiry', 'exam'].includes(String(options.course_type || ''))) form.courseType = options.course_type as CourseType
  if (['beginner', 'intermediate', 'advanced'].includes(String(options.difficulty || ''))) form.difficulty = options.difficulty as DifficultyLevel
  if (options.pedagogy_mode) form.pedagogyMode = options.pedagogy_mode
  if (options.secondary_mode) form.secondaryMode = options.secondary_mode
  if (options.grounding_strategy) form.groundingStrategy = options.grounding_strategy
  form.retrievalEnabled = Boolean(options.retrieval?.enabled)
  form.webMaterialIngest = !options.web_material_ingest?.skip_ingest
  form.generateQuestions = Boolean(options.asset_preferences?.questions || options.asset_preferences?.final_assessment)
  if (options.production_mode) form.productionMode = options.production_mode
  if (typeof options.requirements === 'string') form.requirements = options.requirements
  if (options.target_audience) form.targetAudience = options.target_audience
  if (brief) {
    if (brief.target_audience) form.targetAudience = brief.target_audience
    if (brief.academic_term) form.academicTerm = brief.academic_term
    if (brief.total_class_hours) form.totalClassHours = brief.total_class_hours
    if (brief.lesson_duration_minutes) form.lessonDurationMinutes = brief.lesson_duration_minutes
    form.teachingContext = brief.teaching_context || form.teachingContext
    form.classSize = brief.class_size
    form.classProfile = brief.class_profile || ''
    form.chapterCount = brief.chapter_count
    form.sectionCount = brief.section_count
    if (!form.requirements && brief.additional_requirements) form.requirements = brief.additional_requirements
  }
  if (!intent) return
  if (intent.type === 'project') {
    form.projectGoal = String(intent.project_goal || '')
    form.expectedDeliverable = String(intent.expected_deliverable || '')
    form.priorExperience = String(intent.prior_experience || '')
    form.currentUncertainty = String(intent.current_uncertainty || '')
  } else if (intent.type === 'inquiry') {
    form.coreQuestion = String(intent.core_question || '')
    form.existingUnderstanding = String(intent.existing_understanding || '')
    form.evidenceScope = String(intent.evidence_scope || '')
    form.desiredOutput = String(intent.desired_output || '')
  } else if (intent.type === 'exam') {
    form.examName = String(intent.exam_name || '')
    form.examDate = String(intent.exam_date || '')
    form.examScope = String(intent.exam_scope || '')
    form.currentPreparation = String(intent.current_preparation || '')
  } else if (intent.learning_goal) {
    form.systematicTopic = String(intent.learning_goal)
  }
}
const canSubmit = computed(() => !busy.value && typeIntentComplete.value && Boolean(form.targetAudience.trim())
  && Number.isInteger(form.totalClassHours) && form.totalClassHours >= 1 && form.totalClassHours <= 1000
  && Number.isInteger(form.lessonDurationMinutes) && form.lessonDurationMinutes >= 20 && form.lessonDurationMinutes <= 240
  && (!form.chapterCount || !form.sectionCount || form.sectionCount >= form.chapterCount)
)
watch(() => props.modelValue, async open => {
  if (!open) {
    submissionRequestId.value = ''
    submissionIdentity.value = ''
    return
  }
  const openContextKey = JSON.stringify([props.initialContextKey || '', props.initialSubject, props.initialOptions || {}])
  if (openContextKey !== lastOpenContextKey) {
    resetFormForOpen()
    hydrateInitialOptions(props.initialOptions)
    lastOpenContextKey = openContextKey
  }
  if (!form.systematicTopic.trim() && props.initialSubject.trim()) form.systematicTopic = props.initialSubject.trim()
  if (props.fixedAudience.trim()) form.targetAudience = props.fixedAudience.trim()
  else if (props.initialAudience.trim()) form.targetAudience = props.initialAudience.trim()
  if (props.initialAcademicTerm.trim()) form.academicTerm = props.initialAcademicTerm.trim()
  const initialTotalClassHours = props.initialTotalClassHours
  const initialLessonDurationMinutes = props.initialLessonDurationMinutes
  if (typeof initialTotalClassHours === 'number' && Number.isFinite(initialTotalClassHours) && initialTotalClassHours > 0) form.totalClassHours = initialTotalClassHours
  if (typeof initialLessonDurationMinutes === 'number' && Number.isFinite(initialLessonDurationMinutes) && initialLessonDurationMinutes > 0) form.lessonDurationMinutes = initialLessonDurationMinutes
  if (Number.isFinite(props.initialChapterCount) && Number(props.initialChapterCount) > 0) form.chapterCount = Number(props.initialChapterCount)
  if (Number.isFinite(props.initialSectionCount) && Number(props.initialSectionCount) > 0) form.sectionCount = Number(props.initialSectionCount)
  await nextTick()
  dialogRef.value?.focus()
}, { immediate: true })

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

async function submit() {
  const subject = activeSubject.value
  if (!canSubmit.value) return
  uploading.value = true
  try {
    const materialBindings = materials.value.length
      ? await materialInputRef.value?.ensureUploaded()
      : (props.initialOptions?.material_bindings || [])
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
      production_mode: form.productionMode,
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
      asset_preferences: {
        questions: form.generateQuestions,
        final_assessment: form.generateQuestions,
      },
      requirements: form.requirements.trim(),
      material_bindings: materialBindings || [],
      ...(form.retrievalEnabled && !form.webMaterialIngest
        ? { web_material_ingest: { skip_ingest: true } }
        : {}),
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
    }
    emit('generate', {
      subject,
      options: { ...options, request_id: submissionRequestId.value },
    })
  } catch (error: any) {
    emit('error', error?.message || t('courseGeneration.materials.uploadFailed', '资料上传失败'))
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.generation-dialog-layer { position: fixed; inset: 0; z-index: 520; display: grid; place-items: center; padding: 20px; }
.generation-dialog-layer:has(.generation-dialog--course-space) { padding:24px; }
.generation-dialog-backdrop { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; background: rgba(30, 41, 59, .34); cursor: default; }
.generation-dialog { position: relative; width: min(920px, 100%); max-height: min(860px, calc(100vh - 40px)); display: grid; grid-template-rows: auto minmax(0, 1fr) auto; overflow: hidden; border: 1px solid var(--lz-border); border-radius: 12px; color: var(--lz-text); background: #fff; box-shadow: var(--lz-shadow-overlay); outline: none; }
.generation-dialog__header { min-height: 62px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 0 18px 0 22px; border-bottom: 1px solid var(--lz-border); }
.generation-dialog__heading { min-width: 0; display: grid; gap: 3px; }
.generation-dialog__heading h2 { margin: 0; color: var(--lz-text-strong); font-size: 18px; line-height: 1.25; }
.generation-dialog__heading p { margin:0; color:var(--lz-text-muted); font-size:12px; line-height:1.45; }
.generation-dialog__brand { width:54px; height:54px; display:grid; place-items:center; flex:none; border-radius:18px; color:#fff; background:#6d5dfc; box-shadow:0 12px 26px rgba(109,93,252,.24); }
.icon-button { width: 34px; height: 34px; display: grid; place-items: center; border: 0; border-radius: 7px; color: var(--lz-text-secondary); background: transparent; cursor: pointer; }
.icon-button:hover { color: var(--lz-text-strong); background: var(--lz-surface-muted); }
.generation-dialog__body { min-height: 0; overflow: auto; padding: 4px 24px 24px; }
.form-section { padding: 20px 0; border-bottom: 1px solid rgba(226,232,240,.78); }
.form-section:last-child { border-bottom: 0; }
.form-section--lead { padding-top: 22px; }
.generation-advanced>summary,.supplemental-settings>summary { color:var(--lz-text-secondary); font-size:12px; font-weight:750; cursor:pointer; }
.generation-advanced[open]>summary,.supplemental-settings[open]>summary { margin-bottom:18px; color:var(--lz-brand-strong); }
.supplemental-settings__body { display:grid; gap:18px; padding-top:2px; }
.course-type-section { padding-bottom: 18px; }
.course-type-options { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:4px; padding:4px; border:1px solid rgba(226,232,240,.92); border-radius:11px; background:var(--lz-surface-muted); }
.course-type-option { min-width:0; min-height:48px; display:flex; align-items:center; gap:8px; padding:7px 9px; border:1px solid transparent; border-radius:7px; color:var(--lz-text-secondary); background:transparent; text-align:left; cursor:pointer; transition:border-color .16s ease,color .16s ease,background .16s ease,box-shadow .16s ease; }
.course-type-option:hover:not(:disabled) { border-color:rgba(165,180,252,.62); color:var(--lz-brand-strong); background:rgba(255,255,255,.72); }
.course-type-option.active { border-color:rgba(165,180,252,.72); color:var(--lz-brand-strong); background:#fff; box-shadow:0 2px 7px rgba(79,70,229,.07); }
.course-type-option:focus-visible { outline: 2px solid var(--lz-brand); outline-offset: 2px; }
.course-type-option:disabled { cursor: not-allowed; color: var(--lz-text-muted); background: var(--lz-surface-muted); opacity: .72; }
.course-type-option__icon { width:28px; height:28px; flex:0 0 auto; display:grid; place-items:center; border-radius:7px; color:var(--lz-brand); background:var(--lz-brand-soft); }
.course-type-option:disabled .course-type-option__icon { color: var(--lz-text-muted); background: #fff; }
.course-type-option__copy { min-width:0; display:block; }
.course-type-option__heading { min-width: 0; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; }
.course-type-option__heading strong { color:inherit; font-size:12px; line-height:1.3; }
.course-type-option__heading small { padding: 2px 5px; border-radius: 4px; color: var(--lz-text-muted); background: #fff; font-size:12px; font-weight: 650; }
.course-type-summary,.difficulty-summary { margin:8px 0 0; color:var(--lz-text-muted); font-size:12px; line-height:1.45; }
.intent-section { padding-top: 18px; }
.project-intent { display: grid; gap: 16px; }
.project-intent__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; color: var(--lz-brand-strong); }
.project-intent__heading > div { min-width: 0; display: grid; gap: 4px; }
.project-intent__heading strong { color: var(--lz-text-strong); font-size: 13px; }
.project-intent__heading span { color: var(--lz-text-muted); font-size:12px; line-height: 1.5; }
.project-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.project-field { min-width: 0; }
.project-field--wide { grid-column: 1 / -1; }
.textarea-input--compact { min-height: 72px; }
.starting-point-note { margin: 0; display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; border: 1px solid rgba(99,102,241,.18); border-radius: 8px; color: var(--lz-text-secondary); background: rgba(238,242,255,.58); font-size:12px; line-height: 1.55; }
.starting-point-note svg { flex: 0 0 auto; margin-top: 1px; color: var(--lz-brand-strong); }
.starting-point-note strong { display: block; margin-bottom: 1px; color: var(--lz-text-strong); font-size:12px; }
.web-enrichment-setting__control { display: flex; align-items: flex-start; gap: 11px; cursor: pointer; }
.web-enrichment-setting__control input { margin-top: 3px; accent-color: var(--lz-brand-strong); }
.web-enrichment-setting__control span { display: grid; gap: 4px; }
.web-enrichment-setting__control strong { color: var(--lz-text-strong); font-size: 13px; }
.web-enrichment-setting__control small { color: var(--lz-text-muted); font-size:12px; line-height: 1.55; }
.guided-intro { display:grid; gap:14px; }
.guided-intro__heading { display:flex; align-items:baseline; justify-content:space-between; gap:18px; }
.guided-intro__heading strong { color:var(--lz-text-strong); font-size:12px; }
.guided-intro__heading span { color:var(--lz-text-muted); font-size:12px; text-align:right; }
.guided-intro__steps { margin:0; padding:0; display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); list-style:none; }
.guided-intro__steps li { position:relative; min-width:0; display:grid; justify-items:center; gap:6px; color:var(--lz-text-secondary); font-size:12px; text-align:center; }
.guided-intro__steps li:not(:last-child)::after { content:""; position:absolute; top:12px; left:calc(50% + 16px); right:calc(-50% + 16px); height:1px; background:var(--lz-border); }
.guided-intro__steps span { position:relative; z-index:1; width:25px; height:25px; display:grid; place-items:center; border:1px solid rgba(99,102,241,.24); border-radius:50%; color:var(--lz-brand-strong); background:#fff; font-family:ui-monospace,monospace; font-weight:750; }
.guided-intro__steps strong { overflow:hidden; max-width:100%; text-overflow:ellipsis; white-space:nowrap; }
.teaching-settings { display: grid; gap: 22px; }
.teaching-settings__core { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 32px; }
.teaching-settings__core--common { align-items: start; }
.teaching-settings__core--common .strategy-settings { padding-top: 0; border-top: 0; }
.choice-group { min-width: 0; margin: 0; padding: 0; border: 0; }
.choice-group__title { width: 100%; display: flex; align-items: center; gap: 8px; margin: 0 0 11px; padding: 0; color: var(--lz-text); font-size: 12px; font-weight: 750; }
.choice-group__title > span:last-child { display:grid; gap:2px; }
.choice-group__title small { color:var(--lz-text-muted); font-size:12px; font-weight:500; line-height:1.35; }
.field-icon { width: 25px; height: 25px; display: grid; place-items: center; border: 1px solid; border-radius: 8px; box-shadow: 0 2px 7px rgba(15,23,42,.04); }
.field-icon--amber { border-color: #fde7b0; color: #d97706; background: #fffbeb; }
.field-icon--rose { border-color: #fbcfe8; color: #db2777; background: #fdf2f8; }
.difficulty-options { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:4px; padding:4px; border:1px solid rgba(226,232,240,.92); border-radius:10px; background:var(--lz-surface-muted); }
.difficulty-option { min-width:0; min-height:40px; display:grid; place-items:center; padding:6px 8px; border:1px solid transparent; border-radius:7px; color:var(--lz-text-secondary); background:transparent; text-align:center; cursor:pointer; transition:border-color .16s ease,color .16s ease,background .16s ease,box-shadow .16s ease; }
.difficulty-option:hover:not(:disabled) { border-color:rgba(165,180,252,.62); color:var(--lz-brand-strong); background:rgba(255,255,255,.72); }
.difficulty-option.active { border-color:rgba(165,180,252,.72); color:var(--lz-brand-strong); background:#fff; box-shadow:0 2px 7px rgba(79,70,229,.07); }
.difficulty-option__copy { min-width: 0; display: block; }
.difficulty-option__copy strong { display:block; color:inherit; font-size:12px; }
.difficulty-option:disabled { cursor: not-allowed; opacity: .6; }
.production-mode-options { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
.production-mode-options button { min-width:0; min-height:64px; display:grid; gap:4px; padding:10px 12px; border:1px solid var(--lz-border); border-radius:9px; color:var(--lz-text-secondary); background:#fff; text-align:left; cursor:pointer; }
.production-mode-options button:hover:not(:disabled) { border-color:var(--lz-brand-border); color:var(--lz-brand-strong); }
.production-mode-options button.active { border-color:var(--lz-brand); color:var(--lz-brand-strong); background:var(--lz-brand-soft); box-shadow:inset 0 0 0 1px rgba(99,102,241,.08); }
.production-mode-options button:focus-visible { outline:2px solid var(--lz-brand); outline-offset:2px; }
.production-mode-options button:disabled { opacity:.55; cursor:not-allowed; }
.production-mode-options strong { font-size:12px; }
.production-mode-options small { color:var(--lz-text-muted); font-size:12px; line-height:1.4; }
.strategy-settings { padding-top: 18px; border-top: 1px dashed rgba(203,213,225,.72); }
.strategy-settings__heading { display: flex; align-items: baseline; gap: 9px; margin-bottom: 11px; }
.strategy-settings__heading strong { color: var(--lz-text); font-size: 12px; }
.strategy-settings__heading span { color: var(--lz-text-muted); font-size:12px; }
.teacher-brief-section { display:grid; gap:14px; }
.teacher-brief-section__heading { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; color:var(--lz-brand-strong); }
.teacher-brief-section__heading > div { min-width:0; display:grid; gap:4px; }
.teacher-brief-section__heading strong { color:var(--lz-text); font-size:13px; }
.teacher-brief-section__heading span { color:var(--lz-text-muted); font-size:12px; line-height:1.5; }
.teacher-brief-section__core,.teacher-brief-section__advanced-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.fixed-audience-field { display:grid; align-content:center; min-height:42px; padding:7px 11px; border:1px solid var(--lz-border); border-radius:8px; background:var(--lz-surface-muted); }
.fixed-audience-field .field-label { margin:0 0 2px; color:var(--lz-text-muted); font-size:10px; }
.fixed-audience-field strong { color:var(--lz-text-strong); font-size:12px; }
.teacher-brief-section__advanced { min-width:0; padding-top:12px; border-top:1px solid rgba(226,232,240,.78); }
.teacher-brief-section__advanced summary { color:var(--lz-text-secondary); font-size:12px; font-weight:700; cursor:pointer; }
.teacher-brief-section__advanced[open] summary { margin-bottom:14px; color:var(--lz-brand-strong); }
.teacher-brief-section__advanced-body { display:grid; gap:12px; }
.teacher-brief-section__profile { display:grid; gap:0; }
.compact-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }
.compact-grid--course-space { grid-template-columns:minmax(0,1fr); }
.field-label { display: block; margin-bottom: 8px; color: var(--lz-text); font-size: 12px; font-weight: 700; }
.compact-grid .field-label { display: flex; align-items: center; gap: 6px; color: var(--lz-text-secondary); font-size:12px; }
.text-input,.select-input,.textarea-input { width: 100%; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text-strong); background: #fff; outline: none; transition: border-color .16s ease, box-shadow .16s ease; }
.text-input:focus,.select-input:focus,.textarea-input:focus { border-color: var(--lz-brand); box-shadow: 0 0 0 3px rgba(99,102,241,.1); }
.text-input:disabled,.select-input:disabled,.textarea-input:disabled { cursor: not-allowed; opacity: .6; }
.text-input { height: 42px; padding: 0 12px; }
.text-input--large { height: 48px; font-size: 15px; }
.select-input { height: 38px; padding: 0 9px; font-size: 12px; }
.textarea-input { min-height: 82px; padding: 10px 12px; resize: vertical; line-height: 1.6; font-size: 12px; }
.field-help { margin: 7px 0 0; color: var(--lz-text-muted); font-size:12px; line-height: 1.5; }
.segmented-options { display: grid; gap: 8px; }
.segmented-options--three { grid-template-columns: repeat(3, 1fr); }
.segmented-options--two { grid-template-columns: repeat(2, 1fr); }
.segmented-options button { min-width: 0; min-height: 66px; display: flex; align-items: center; justify-content: flex-start; gap: 10px; padding: 10px 12px; border: 1px solid var(--lz-border); border-radius: 8px; color: var(--lz-text-secondary); background: #fff; text-align: left; cursor: pointer; }
.segmented-options button:hover { border-color: rgba(99,102,241,.46); }
.segmented-options button.active { border-color: var(--lz-brand); color: var(--lz-brand-strong); background: var(--lz-brand-soft); box-shadow: inset 0 0 0 1px rgba(99,102,241,.1); }
.segmented-options button:disabled { cursor: not-allowed; opacity: .6; }
.segmented-options strong { display: block; color: inherit; font-size: 12px; }
.segmented-options span { min-width: 0; display: block; color: var(--lz-text-muted); font-size:12px; line-height: 1.45; }
.segmented-options span strong { margin-bottom: 2px; }
.material-section :deep(section) { margin: 0; }
.generation-dialog__footer { min-height: 64px; display: flex; align-items: center; justify-content: flex-end; gap: 18px; padding: 10px 18px; border-top: 1px solid var(--lz-border); background: #fff; }
.footer-actions { display: flex; gap: 8px; flex: 0 0 auto; }
.primary-button,.secondary-button { min-height: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 0 15px; border-radius: 8px; font-size: 12px; font-weight: 700; cursor: pointer; }
.primary-button { border: 1px solid var(--lz-brand-strong); color: #fff; background: var(--lz-brand-strong); }
.secondary-button { border: 1px solid var(--lz-border); color: var(--lz-text-secondary); background: #fff; }
.primary-button:disabled,.secondary-button:disabled { cursor: not-allowed; opacity: .55; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.generation-dialog--course-space { width:min(920px,100%); height:auto; max-height:min(760px,calc(100vh - 48px)); border:1px solid var(--lz-border); border-radius:16px; box-shadow:0 20px 60px rgba(15,23,42,.2); }
.generation-dialog--course-space .generation-dialog__header { min-height:64px; justify-content:flex-start; padding:0 16px 0 20px; border-bottom-color:#edf0f5; }
.generation-dialog--course-space .generation-dialog__brand { width:38px; height:38px; border-radius:12px; box-shadow:0 8px 18px rgba(109,93,252,.2); }
.generation-dialog--course-space .generation-dialog__heading { flex:1; }
.generation-dialog--course-space .generation-dialog__heading h2 { color:#29256f; font-size:20px; font-weight:820; letter-spacing:-.02em; }
.generation-dialog--course-space .icon-button { color:#8b97aa; }
.generation-dialog--course-space .generation-dialog__body { padding:4px 28px 24px; }
.generation-dialog--course-space .form-section { padding:18px 0; border-bottom-color:#edf0f5; }
.generation-dialog--course-space .form-section--lead { padding-top:20px; }
.generation-dialog--course-space .intent-section { padding-bottom:10px; border-bottom:0; }
.generation-dialog--course-space .course-goal-section { padding-top:2px; }
.generation-dialog--course-space .generation-advanced>summary { margin-bottom:18px; color:#344054; font-size:12px; font-weight:800; list-style:none; pointer-events:none; }
.generation-dialog--course-space .generation-advanced>summary::-webkit-details-marker { display:none; }
.generation-dialog--course-space .teaching-settings { gap:0; }
.generation-dialog--course-space .teaching-settings__core { gap:24px; }
.generation-dialog--course-space .strategy-settings { padding-top:0; border-top:0; }
.generation-dialog--course-space .production-mode-options button { min-height:58px; align-content:center; justify-items:start; padding-inline:14px; text-align:left; }
.generation-dialog--course-space .teacher-brief-section__core { grid-template-columns:repeat(3,minmax(0,1fr)); }
.generation-dialog--course-space .generation-dialog__footer { min-height:60px; padding:10px 18px; border-top-color:#edf0f5; background:#fbfcff; }
.generation-dialog--course-space .primary-button { min-width:156px; border-color:#6757ef; background:#6757ef; box-shadow:0 8px 18px rgba(103,87,239,.18); }
@media (max-width: 760px) {
  .generation-dialog-layer,.generation-dialog-layer:has(.generation-dialog--course-space) { align-items: end; padding: 0; }
  .generation-dialog { width: 100%; max-height: calc(100vh - 56px); border-radius: 14px 14px 0 0; }
  .generation-dialog__body { padding-inline: 16px; }
  .teaching-settings__core { grid-template-columns: 1fr; gap: 22px; }
  .course-type-options { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .compact-grid { grid-template-columns: 1fr 1fr; }
  .teacher-brief-section__core,.teacher-brief-section__advanced-grid { grid-template-columns:1fr; }
  .generation-dialog__footer { align-items: stretch; flex-direction: column; padding: 10px 16px 14px; }
  .footer-actions,.footer-actions button { width: 100%; }
  .footer-actions button { flex: 1; }
  .generation-dialog--course-space { height:auto; max-height:calc(100dvh - 24px); border-radius:20px 20px 0 0; }
  .generation-dialog--course-space .generation-dialog__header { min-height:64px; padding:0 14px; }
  .generation-dialog--course-space .generation-dialog__brand { width:36px; height:36px; border-radius:11px; }
  .generation-dialog--course-space .generation-dialog__heading h2 { font-size:18px; }
  .generation-dialog--course-space .generation-dialog__body { padding:2px 16px 18px; }
  .generation-dialog--course-space .course-type-options { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .generation-dialog--course-space .teaching-settings__core { gap:24px; }
  .generation-dialog--course-space .teacher-brief-section__core { grid-template-columns:1fr; }
  .generation-dialog--course-space .generation-dialog__footer { padding:10px 16px 14px; }
}
@media (max-width: 520px) {
  .guided-intro__steps { grid-template-columns: repeat(3, minmax(0, 1fr)); row-gap: 12px; }
  .guided-intro__steps li:nth-child(3n)::after { display: none; }
  .segmented-options--three,.segmented-options--two,.compact-grid { grid-template-columns: 1fr; }
  .course-type-options { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .course-type-option { min-height:44px; }
  .choice-group__title small { display:none; }
  .course-type-summary { min-height:29px; }
  .project-fields { grid-template-columns: 1fr; }
  .production-mode-options { grid-template-columns:1fr; }
  .project-field--wide { grid-column: auto; }
  .segmented-options button { min-height: 52px; }
  .strategy-settings__heading { align-items: flex-start; flex-direction: column; gap: 3px; }
}
</style>
