<template>
  <article
    class="deck-canvas"
    :class="{ 'is-presenting': presenting }"
    :data-layout="visualLayout"
    :data-layout-contract="v5LayoutNames.has(visualLayout) ? layoutContract.schema_version : undefined"
    :data-heading-mode="headingMode"
    :data-task-prompt-mode="slide.quality?.task_prompt_mode || undefined"
    :data-task-prompt-phase="slide.quality?.task_prompt_phase || undefined"
    :data-theme="theme"
    :data-template-rich="richTemplate ? 'true' : undefined"
    :style="themeStyle"
    :aria-label="`${pageNumber} / ${pageCount} · ${slide.title}`"
  >
    <template v-if="slide.layout === 'cover'">
      <div v-if="visualLayout !== 'cover-minimal'" class="deck-cover__wash"></div>
      <div v-if="visualLayout !== 'cover-minimal'" class="deck-cover__index">{{ String(pageNumber).padStart(2, '0') }}</div>
      <div v-if="visualLayout !== 'cover-minimal'" class="deck-cover__brand">{{ t('teachingRepresentations.slides.brand', '启智') }}</div>
      <div class="deck-cover__content">
        <small>{{ slide.eyebrow || t('teachingRepresentations.slides.courseDeck', '课堂演示') }}</small>
        <h2>{{ slide.title }}</h2>
        <p v-if="slide.subtitle">{{ slide.subtitle }}</p>
        <blockquote v-if="slide.key_message">{{ slide.key_message }}</blockquote>
      </div>
      <footer><span>{{ t('teachingRepresentations.slides.sameSourceDeck', '同源课程课件') }}</span><span>{{ pageNumber }} / {{ pageCount }}</span></footer>
    </template>

    <template v-else-if="slide.layout === 'chapter'">
      <div class="deck-chapter__panel">
        <small>{{ t('teachingRepresentations.slides.chapter', 'CHAPTER') }}</small>
        <strong>{{ chapterNumber(slide.title) }}</strong>
      </div>
      <div class="deck-chapter__content">
        <small>{{ slide.eyebrow }}</small>
        <h2>{{ slide.title }}</h2>
        <i></i>
        <blockquote>{{ slide.key_message || slide.teaching_job || slide.takeaway }}</blockquote>
      </div>
      <footer><span>{{ deckTitle }}</span><span>{{ pageNumber }} / {{ pageCount }}</span></footer>
    </template>

    <template v-else>
      <header class="deck-canvas__heading">
        <div>
          <small>{{ sectionLabel || slide.eyebrow || layoutLabel(visualLayout) }}</small>
          <h2 v-if="headingMode !== 'hidden'">{{ displayHeading }}</h2>
        </div>
        <span>{{ String(pageNumber).padStart(2, '0') }}</span>
      </header>

      <blockquote
        v-if="showsStandaloneMessage"
        class="deck-canvas__message"
      >
        {{ slide.key_message }}
      </blockquote>

      <div
        v-if="showsVisualStory"
        class="deck-canvas__story"
        :data-composition="resolvedComposition"
        :data-layout-variant="slide.quality?.v6_layout_variant || undefined"
        :data-source-empty="sourceBlocks.length === 0"
        :data-density="sourceCharacterCount > 180 ? 'dense' : 'normal'"
        :data-has-message="showsStandaloneMessage"
      >
        <SlideVisualRenderer
          :visuals="slide.visuals ?? []"
          :course-id="courseId"
          :representation-id="representationId"
        />
        <div v-if="sourceBlocks.length" class="deck-canvas__source">
          <small>{{ slide.teaching_job }}</small>
          <section v-for="block in sourceBlocks" :key="block.block_id" :data-type="block.type">
            <b v-if="block.title">{{ block.title }}</b>
            <pre v-if="block.type === 'code'"><code>{{ block.content }}</code></pre>
            <ol v-else-if="block.type === 'process'">
              <li v-for="(item, itemIndex) in block.items" :key="item">
                <i>{{ itemIndex + 1 }}</i>
                <MarkdownRenderer :content="item" :enable-code-run="false" />
              </li>
            </ol>
            <ul v-else-if="block.items?.length">
              <li v-for="item in block.items" :key="item">
                <MarkdownRenderer :content="item" :enable-code-run="false" />
              </li>
            </ul>
            <MarkdownRenderer
              v-else
              class="deck-inline-markdown"
              :content="block.content || ''"
              :enable-code-run="false"
            />
          </section>
        </div>
      </div>

      <div
        v-else-if="visualLayout === 'hero-claim'"
        class="deck-hero-claim"
      >
        <i></i>
        <strong>{{ semanticItems[0] || slide.key_message || slide.takeaway || slide.title }}</strong>
      </div>

      <div
        v-else-if="slide.quality?.suppress_redundant_body"
        class="deck-claim-only"
      >
        <i></i>
        <small>{{ slide.teaching_job || slide.eyebrow || '核心判断' }}</small>
      </div>

      <div
        v-else-if="visualLayout === 'parallel-examples'"
        class="deck-parallel-examples"
        :data-has-message="showsStandaloneMessage"
      >
        <article v-for="(item, index) in semanticItems.slice(0, 4)" :key="`${index}-${item}`">
          <b>{{ String(index + 1).padStart(2, '0') }}</b>
          <MarkdownRenderer :content="item" :enable-code-run="false" />
        </article>
      </div>

      <div
        v-else-if="visualLayout === 'question-prompt'"
        class="deck-question-prompt"
        :data-has-message="showsStandaloneMessage"
      >
        <small>{{ taskPromptLabel }}</small>
        <div class="deck-question-prompt__items">
          <MarkdownRenderer
            v-for="item in questionPromptItems"
            :key="item"
            :content="item"
            :enable-code-run="false"
          />
        </div>
      </div>

      <div
        v-else-if="visualLayout === 'worked-example'"
        class="deck-worked-example"
        :data-has-message="showsStandaloneMessage"
      >
        <article v-for="(item, index) in semanticItems.slice(0, 3)" :key="`${index}-${item}`">
          <b>{{ index + 1 }}</b>
          <small>{{ workedStepLabel(index) }}</small>
          <MarkdownRenderer :content="item" :enable-code-run="false" />
        </article>
      </div>

      <div
        v-else-if="visualLayout === 'practice-feedback'"
        class="deck-practice-feedback"
        :data-has-message="showsStandaloneMessage"
        :data-feedback-mode="practiceFeedbackMode"
      >
        <template v-if="practiceFeedbackMode === 'shared_evidence'">
          <section class="deck-practice-feedback__questions">
            <article
              v-for="(prompt, index) in practicePromptItems"
              :key="`${index}-${prompt}`"
              class="deck-practice-feedback__question"
            >
              <small>问题 {{ String(index + 1).padStart(2, '0') }}</small>
              <MarkdownRenderer :content="prompt" :enable-code-run="false" />
            </article>
          </section>
          <aside class="deck-practice-feedback__evidence">
            <small>判断依据</small>
            <ul>
              <li v-for="(item, index) in practiceFeedbackItems" :key="`${index}-${item}`">
                <MarkdownRenderer :content="item" :enable-code-run="false" />
              </li>
            </ul>
          </aside>
        </template>
        <template v-else>
          <article
            v-for="(pair, index) in practiceFeedbackPairs"
            :key="`${index}-${pair.prompt}`"
            class="deck-practice-feedback__pair"
          >
            <section>
              <small>问题 {{ String(index + 1).padStart(2, '0') }}</small>
              <MarkdownRenderer :content="pair.prompt" :enable-code-run="false" />
            </section>
            <aside>
              <small>回答与判断依据</small>
              <MarkdownRenderer
                v-if="pair.feedback"
                :content="pair.feedback"
                :enable-code-run="false"
              />
            </aside>
          </article>
        </template>
      </div>

      <div
        v-else-if="visualLayout === 'chapter-recap'"
        class="deck-chapter-recap"
        :data-has-message="showsStandaloneMessage"
      >
        <article v-for="(item, index) in semanticItems.slice(0, 4)" :key="`${index}-${item}`">
          <b>{{ String(index + 1).padStart(2, '0') }}</b>
          <MarkdownRenderer :content="item" :enable-code-run="false" />
        </article>
      </div>

      <div
        v-else-if="visualLayout === 'course-synthesis'"
        class="deck-course-synthesis"
        :data-has-message="showsStandaloneMessage"
      >
        <aside>
          <small>课程主线</small>
          <strong>{{ slide.key_message || slide.takeaway || slide.title }}</strong>
        </aside>
        <ol>
          <li v-for="(item, index) in semanticItems.slice(0, 6)" :key="`${index}-${item}`">
            <b>{{ String(index + 1).padStart(2, '0') }}</b>
            <MarkdownRenderer :content="item" :enable-code-run="false" />
          </li>
        </ol>
      </div>

      <div
        v-else-if="visualLayout === 'editorial-body' && slide.blocks?.length"
        class="deck-editorial-body"
        :data-has-message="showsStandaloneMessage"
      >
        <section
          v-for="block in slide.blocks"
          :key="block.block_id"
          class="deck-editorial-body__group"
          :data-type="block.type"
        >
          <small v-if="block.title">{{ block.title }}</small>
          <pre v-if="block.type === 'code'"><code>{{ block.content }}</code></pre>
          <ul v-else-if="block.items?.length">
            <li v-for="item in block.items" :key="item">
              <MarkdownRenderer :content="item" :enable-code-run="false" />
            </li>
          </ul>
          <MarkdownRenderer
            v-else
            class="deck-inline-markdown"
            :content="block.content || ''"
            :enable-code-run="false"
          />
        </section>
      </div>

      <div
        v-else-if="slide.blocks?.length"
        class="deck-canvas__blocks"
        :data-layout="visualLayout"
        :data-count="slide.blocks?.length || 0"
        :data-has-message="showsStandaloneMessage"
      >
        <section v-for="(block, blockIndex) in slide.blocks" :key="block.block_id" :data-type="block.type">
          <header v-if="block.title">
            <b>{{ String(blockIndex + 1).padStart(2, '0') }}</b>
            <span>{{ block.title }}</span>
          </header>
          <pre v-if="block.type === 'code'"><code>{{ block.content }}</code></pre>
          <table v-else-if="block.type === 'comparison' && block.metadata?.rows?.length">
            <thead>
              <tr><th v-for="header in block.metadata.headers || []" :key="header">{{ header }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIndex) in block.metadata.rows" :key="rowIndex">
                <td v-for="cell in row" :key="cell">{{ cell }}</td>
              </tr>
            </tbody>
          </table>
          <ol v-else-if="block.type === 'process'">
            <li v-for="(item, itemIndex) in block.items" :key="item">
              <b>{{ itemIndex + 1 }}</b>
              <MarkdownRenderer :content="item" :enable-code-run="false" />
            </li>
          </ol>
          <div
            v-else-if="visualLayout === 'classification-3' && block.items?.length === 3"
            class="deck-classification"
          >
            <article
              v-for="(item, itemIndex) in block.items"
              :key="item"
              class="deck-classification__item"
            >
              <b>{{ String(itemIndex + 1).padStart(2, '0') }}</b>
              <MarkdownRenderer :content="item" :enable-code-run="false" />
            </article>
          </div>
          <ul v-else-if="block.items?.length">
            <li v-for="item in block.items" :key="item">
              <MarkdownRenderer :content="item" :enable-code-run="false" />
            </li>
          </ul>
          <MarkdownRenderer
            v-else
            class="deck-inline-markdown"
            :content="block.content || ''"
            :enable-code-run="false"
          />
        </section>
      </div>

      <div v-else class="deck-canvas__navigation">
        <i></i>
        <small>{{ navigationPrefix }}</small>
        <strong>{{ navigationDetail }}</strong>
        <p>先明确问题，再连接概念、方法与检验。</p>
      </div>

      <footer>
        <span>{{ slide.section_id || deckTitle }}</span>
        <span>{{ pageNumber }} / {{ pageCount }}</span>
      </footer>
    </template>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../shared/i18n'
import type { SlideDeckTheme } from '../stores/teachingRepresentations'
import SlideVisualRenderer from './SlideVisualRenderer.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import themePack from '../data/slide-themes.json'
import layoutContract from '../../../shared/slide-layout-contract-v5.json'
import type { SlideVisual } from '../types/slideVisual'
import { resolvePublicAssetUrl } from '../utils/publicAssetUrl'

interface SlideBlock {
  block_id: string
  type: string
  title?: string
  content?: string
  items?: string[]
  metadata?: Record<string, any>
}

interface Slide {
  layout: string
  eyebrow?: string
  title: string
  subtitle?: string
  key_message?: string
  teaching_job?: string
  takeaway?: string
  transition_from?: string
  composition?: string
  visuals?: SlideVisual[]
  section_id?: string
  blocks: SlideBlock[]
  quality?: {
    passed?: boolean
    character_count?: number
    issues?: Array<Record<string, any>>
    requested_layout?: string
    resolved_layout?: string
    requested_composition?: string
    resolved_composition?: string
    suppress_redundant_body?: boolean
    worked_step_labels?: string[]
    heading_mode?: 'full' | 'hidden'
    section_label?: string
    feedback_mode?: 'paired' | 'shared_evidence' | 'task_only'
    prompt_label?: string
    task_prompt_mode?: 'action' | 'verification'
    task_prompt_phase?: 'overview' | 'procedure' | 'verification'
    final_page_contract_version?: string
    final_page_contract_v2?: Record<string, any>
    manual_edit_required?: boolean
    manual_edit_reasons?: Array<Record<string, any>>
    v6_layout_variant?: string
    v6_artifact_support_mode?: 'split' | 'full' | ''
  }
}

const props = withDefaults(defineProps<{
  slide: Slide
  pageNumber: number
  pageCount: number
  deckTitle: string
  theme?: SlideDeckTheme
  themeOverrides?: Record<string, string>
  presenting?: boolean
  courseId?: string
  representationId?: string
}>(), {
  theme: 'qingfeng-classroom',
  themeOverrides: () => ({}),
  presenting: false,
  courseId: '',
  representationId: '',
})

const visualLayout = computed(() => {
  const quality = props.slide.quality
  const carriesFinalV5Contract = Boolean(
    quality?.final_page_contract_v2
    || quality?.final_page_contract_version?.startsWith('final_page_contract_v5'),
  )
  if (carriesFinalV5Contract && !quality?.resolved_layout) return 'v5-layout-missing'
  return quality?.resolved_layout || quality?.requested_layout || props.slide.layout
})
const headingMode = computed<'full' | 'hidden'>(() => (
  props.slide.quality?.heading_mode === 'hidden' ? 'hidden' : 'full'
))
const sectionLabel = computed(() => {
  const explicit = String(props.slide.quality?.section_label || '')
  if (explicit) return explicit
  const message = String(props.slide.key_message || '').trim()
  return /^\d+(?:[.．]\d+)+\s+\S+/.test(message) ? message : ''
})
const showsStandaloneMessage = computed(() => {
  const message = String(props.slide.key_message || '').trim()
  if (!message || message === sectionLabel.value) return false
  if (['hero-claim', 'question-prompt', 'practice-feedback'].includes(visualLayout.value)) {
    return false
  }
  return !['objective', 'misconception', 'practice'].includes(props.slide.layout)
})
const v5LayoutNames = new Set(
  layoutContract.layouts.map(item => item.layout),
)
const resolvedComposition = computed(() => (
  props.slide.quality?.resolved_composition
  || props.slide.composition
  || 'statement'
))
const sourceBlocks = computed(() => {
  const visualKind = props.slide.visuals?.[0]?.kind
  const blocks = props.slide.blocks || []
  if (visualKind === 'formula') {
    return blocks.filter(block => block.type !== 'formula' && !block.metadata?.formula)
  }
  if (visualKind === 'table') {
    if (props.slide.quality?.v6_artifact_support_mode === 'full') return []
    return blocks.filter(block => !block.metadata?.table_source)
  }
  return blocks
})
const sourceCharacterCount = computed(() => sourceBlocks.value.reduce(
  (total, block) => total
    + String(block.title || '').length
    + String(block.content || '').length
    + (block.items || []).reduce((sum, item) => sum + String(item).length, 0),
  0,
))
const semanticItems = computed(() => (props.slide.blocks || []).flatMap((block) => {
  if (block.items?.length) return block.items.filter(Boolean)
  return block.content ? [block.content] : []
}))
function blockItems(block: SlideBlock | undefined) {
  if (!block) return []
  if (block.items?.length) return block.items.filter(Boolean)
  return block.content ? [block.content] : []
}
const questionPromptItems = computed(() => (
  semanticItems.value.length
    ? semanticItems.value.slice(0, 3)
    : [props.slide.key_message || ''].filter(Boolean)
))
const taskPromptLabel = computed(() => (
  String(props.slide.quality?.prompt_label || '先独立判断')
))
const practicePromptBlock = computed(() => (
  (props.slide.blocks || []).find(block => (
    block.metadata?.semantic_role === 'prompt'
    || ['exercise', 'question', 'prompt'].includes(block.type)
  ))
))
const visualDirectedLayouts = new Set([
  'figure-text',
  'diagram-full',
  'formula-explanation',
  'data-highlight',
])
const showsVisualStory = computed(() => Boolean(
  props.slide.visuals?.length
  && (
    visualDirectedLayouts.has(visualLayout.value)
    || !v5LayoutNames.has(visualLayout.value)
  )
))
const practicePromptEntries = computed(() => {
  const prompt = practicePromptBlock.value
  const questionIds = Array.isArray(prompt?.metadata?.question_ids)
    ? prompt?.metadata?.question_ids.map(String)
    : []
  return blockItems(prompt).slice(0, 3).map((text, index) => ({
    id: questionIds[index] || `question-${index}`,
    text,
  }))
})
const practicePromptItems = computed(() => (
  practicePromptEntries.value.map(item => item.text)
))
const practiceFeedbackBlocks = computed(() => {
  const blocks = props.slide.blocks || []
  const explicit = blocks.filter(block => (
      ['answer', 'feedback', 'solution', 'validation'].includes(
        String(block.metadata?.semantic_role || ''),
      )
      || ['answer', 'feedback', 'solution', 'validation'].includes(block.type)
  ))
  return explicit.length
    ? explicit
    : blocks.filter(block => !(
        block.metadata?.semantic_role === 'prompt'
        || ['exercise', 'question', 'prompt'].includes(block.type)
      ))
})
const practiceFeedbackItems = computed(() => (
  practiceFeedbackBlocks.value
    .flatMap(block => blockItems(block))
    .slice(0, 4)
))
const practiceAnswerEntries = computed(() => practiceFeedbackBlocks.value.flatMap((block) => {
  const answerForIds = Array.isArray(block.metadata?.answer_for_question_ids)
    ? block.metadata?.answer_for_question_ids.map(String)
    : []
  return blockItems(block).map((text, index) => ({
    questionId: answerForIds[index] || '',
    text,
  }))
}))
const practiceFeedbackPairs = computed(() => practicePromptEntries.value.map(
  (prompt, index) => ({
    prompt: prompt.text,
    feedback: practiceAnswerEntries.value.find(
      answer => answer.questionId === prompt.id,
    )?.text || practiceAnswerEntries.value[index]?.text || '',
  }),
))
const practiceFeedbackMode = computed<'paired' | 'shared_evidence'>(() => (
  props.slide.quality?.feedback_mode === 'shared_evidence'
    ? 'shared_evidence'
    : 'paired'
))
const headingSubscripts: Record<string, string> = {
  0: '₀', 1: '₁', 2: '₂', 3: '₃', 4: '₄',
  5: '₅', 6: '₆', 7: '₇', 8: '₈', 9: '₉',
  i: 'ᵢ', j: 'ⱼ', k: 'ₖ', n: 'ₙ',
}
function formatHeading(value: string) {
  return value
    .replace(/^(?:\$\$|\\\[|\\\()/, '')
    .replace(/(?:\$\$|\\\]|\\\))$/, '')
    .replace(/\\mathbb\{([A-Za-z])\}/g, '$1')
    .replace(/\\(?:mathbf|mathrm|operatorname|text)\{([^{}]+)\}/g, '$1')
    .replace(/\\subseteq/g, '⊆')
    .replace(/\\cap/g, '∩')
    .replace(/\\cup/g, '∪')
    .replace(/\\in(?![A-Za-z])/g, '∈')
    .replace(/\\mid/g, '∣')
    .replace(/\\land/g, '∧')
    .replace(/\\lor/g, '∨')
    .replace(/\\sum/g, '∑')
    .replace(/\\Sigma/g, 'Σ')
    .replace(/\\cdots/g, '⋯')
    .replace(/\\times/g, '×')
    .replace(/\\leq/g, '≤')
    .replace(/\\geq/g, '≥')
    .replace(/\\approx/g, '≈')
    .replace(/\\neq/g, '≠')
    .replace(/\\left|\\right/g, '')
    .replace(/\\\{/g, '{')
    .replace(/\\\}/g, '}')
    .replace(/[{}]/g, '')
    .replace(/_([0-9ijkn])/g, (_match, token: string) => headingSubscripts[token] || token)
    .replace(/\s+/g, ' ')
    .trim()
}
function headingExcerpt(value: string, limit = 18) {
  const clean = formatHeading(value).replace(/[，,；;：:。…\s]+$/g, '')
  if (clean.length <= limit) return clean
  let excerpt = clean.slice(0, limit)
  const opening = Math.max(excerpt.lastIndexOf('（'), excerpt.lastIndexOf('('))
  const closing = Math.max(excerpt.lastIndexOf('）'), excerpt.lastIndexOf(')'))
  if (opening > closing && opening >= Math.max(8, Math.floor(limit / 3))) {
    excerpt = excerpt.slice(0, opening)
  } else {
    const punctuation = ['。', '；', '，', '：', '）', ')']
      .map(mark => ({ index: excerpt.lastIndexOf(mark), mark }))
      .sort((a, b) => b.index - a.index)[0]
    if (punctuation && punctuation.index >= Math.max(10, Math.floor(limit / 2))) {
      excerpt = excerpt.slice(
        0,
        punctuation.index + (['）', ')'].includes(punctuation.mark) ? 1 : 0),
      )
    } else {
      const space = excerpt.lastIndexOf(' ')
      if (space >= Math.max(10, Math.floor(limit / 2))) excerpt = excerpt.slice(0, space)
    }
  }
  return excerpt.replace(/[，,；;：:。…\s]+$/g, '')
}
const displayHeading = computed(() => {
  return headingExcerpt(props.slide.title, 18)
})
const navigationText = computed(() => String(
  props.slide.teaching_job
  || props.slide.key_message
  || props.slide.takeaway
  || props.slide.title,
))
const navigationPrefix = computed(() => {
  return ['recap', 'summary'].includes(String(props.slide.layout || ''))
    ? '本章回顾'
    : '本节学习问题'
})
const navigationDetail = computed(() => navigationText.value)
const richTemplate = computed(() => {
  const aliases: Record<string, string> = {
    'qingfeng-classroom': 'qizhi-classroom',
    'academic-bluegray': 'academic-editorial',
  }
  const key = aliases[props.theme] || props.theme
  const token = (themePack.themes as Record<string, Record<string, any>>)[key]
  return Boolean(token?.template?.template_id && token?.visual_assets)
})
const themeStyle = computed(() => {
  const aliases: Record<string, string> = {
    'qingfeng-classroom': 'qizhi-classroom',
    'academic-bluegray': 'academic-editorial',
  }
  const key = aliases[props.theme] || props.theme
  const baseToken = (themePack.themes as Record<string, Record<string, any>>)[key]
  if (!baseToken) return {}
  const token = { ...baseToken, ...props.themeOverrides }
  const visualAssets = token.visual_assets || {}
  const textBoxStyles = token.text_box_styles || {}
  const assetUrl = (value?: string) => resolvePublicAssetUrl(value, import.meta.env.BASE_URL)
  return {
    '--deck-bg': `#${token.surface}`,
    '--deck-paper': `#${token.surface}`,
    '--deck-canvas': `#${token.canvas}`,
    '--deck-title': `#${token.title}`,
    '--deck-ink': `#${token.title}`,
    '--deck-body': `#${token.ink}`,
    '--deck-muted': `#${token.muted}`,
    '--deck-main': `#${token.accent}`,
    '--deck-blue': `#${token.accent}`,
    '--deck-blue-soft': `#${token.accent_soft}`,
    '--deck-teal': `#${token.green}`,
    '--deck-teal-soft': `#${token.green_soft}`,
    '--deck-amber': `#${token.amber}`,
    '--deck-amber-soft': `#${token.amber_soft}`,
    '--deck-red': `#${token.red}`,
    '--deck-red-soft': `#${token.red_soft}`,
    '--deck-card': `#${token.surface}`,
    '--deck-line': `#${token.chart_bg}`,
    '--deck-message-bg': `#${token.accent_soft}`,
    '--deck-callout': `#${token.accent}`,
    '--deck-title-font': `"${token.title_font}","${token.title_east_asian_font}",sans-serif`,
    '--deck-body-font': `"${token.body_font}","${token.body_east_asian_font}",sans-serif`,
    '--deck-card-radius': token.geometry?.card_radius_in
      ? `${Number(token.geometry.card_radius_in) * 7.5}cqw`
      : '1cqw',
    '--deck-cover-image': visualAssets.cover?.web_path
      ? `url("${assetUrl(visualAssets.cover.web_path)}")`
      : 'none',
    '--deck-chapter-image': visualAssets.chapter?.web_path
      ? `url("${assetUrl(visualAssets.chapter.web_path)}")`
      : 'none',
    '--deck-recap-image': visualAssets.recap?.web_path
      ? `url("${assetUrl(visualAssets.recap.web_path)}")`
      : 'none',
    '--deck-content-image': visualAssets.interior_content?.web_path
      ? `url("${assetUrl(visualAssets.interior_content.web_path)}")`
      : 'none',
    '--deck-reasoning-image': visualAssets.interior_reasoning?.web_path
      ? `url("${assetUrl(visualAssets.interior_reasoning.web_path)}")`
      : 'none',
    '--deck-practice-image': visualAssets.interior_practice?.web_path
      ? `url("${assetUrl(visualAssets.interior_practice.web_path)}")`
      : 'none',
    '--deck-evidence-image': visualAssets.interior_evidence?.web_path
      ? `url("${assetUrl(visualAssets.interior_evidence.web_path)}")`
      : 'none',
    '--deck-box-standard': `#${textBoxStyles.standard?.fill || token.surface}`,
    '--deck-box-standard-depth': `#${textBoxStyles.standard?.depth || textBoxStyles.standard?.border || token.chart_bg}`,
    '--deck-box-message': `#${textBoxStyles.message?.fill || token.accent_soft}`,
    '--deck-box-message-depth': `#${textBoxStyles.message?.depth || textBoxStyles.message?.border || token.chart_bg}`,
    '--deck-box-definition': `#${textBoxStyles.definition?.fill || token.surface}`,
    '--deck-box-definition-depth': `#${textBoxStyles.definition?.depth || textBoxStyles.definition?.border || token.chart_bg}`,
    '--deck-box-boundary': `#${textBoxStyles.boundary?.fill || token.green_soft}`,
    '--deck-box-boundary-depth': `#${textBoxStyles.boundary?.depth || textBoxStyles.boundary?.border || token.chart_bg}`,
    '--deck-box-reasoning': `#${textBoxStyles.reasoning?.fill || token.accent_soft}`,
    '--deck-box-reasoning-depth': `#${textBoxStyles.reasoning?.depth || textBoxStyles.reasoning?.border || token.chart_bg}`,
    '--deck-box-practice': `#${textBoxStyles.practice?.fill || token.amber_soft}`,
    '--deck-box-practice-depth': `#${textBoxStyles.practice?.depth || textBoxStyles.practice?.border || token.chart_bg}`,
    '--deck-box-feedback': `#${textBoxStyles.feedback?.fill || token.green_soft}`,
    '--deck-box-feedback-depth': `#${textBoxStyles.feedback?.depth || textBoxStyles.feedback?.border || token.chart_bg}`,
    '--deck-box-misconception': `#${textBoxStyles.misconception?.fill || token.red_soft}`,
    '--deck-box-misconception-depth': `#${textBoxStyles.misconception?.depth || textBoxStyles.misconception?.border || token.chart_bg}`,
    '--deck-box-evidence': `#${textBoxStyles.evidence?.fill || token.title}`,
    '--deck-box-evidence-depth': `#${textBoxStyles.evidence?.depth || textBoxStyles.evidence?.border || token.title}`,
    '--deck-box-note': `#${textBoxStyles.note?.fill || token.surface}`,
    '--deck-box-note-depth': `#${textBoxStyles.note?.depth || textBoxStyles.note?.border || token.chart_bg}`,
  }
})

function chapterNumber(title: string) {
  return title.match(/\d+/)?.[0]?.padStart(2, '0') || '·'
}

function workedStepLabel(index: number) {
  return props.slide.quality?.worked_step_labels?.[index] || `步骤 ${index + 1}`
}

function layoutLabel(value: string) {
  return t(`teachingRepresentations.slides.layouts.${value}`, ({
    cover: '封面',
    roadmap: '路线',
    chapter: '章节',
    objective: '目标',
    concept: '概念',
    'hero-statement': '核心判断',
    'editorial-body': '正文',
    'two-column': '双栏推理',
    'balanced-two-column': '双栏推理',
    'classification-3': '三项分类',
    'agenda-linear': '课程路线',
    'chapter-entry': '章节导入',
    'chapter-recap': '章节回顾',
    'course-synthesis': '课程总结',
    'parallel-examples': '并列应用',
    'question-prompt': '理解检查',
    'case-study': '案例',
    question: '思考',
    summary: '回顾',
    comparison: '对比',
    process: '过程',
    code: '代码',
    misconception: '易错',
    practice: '练习',
    recap: '小结',
    appendix: '附录',
  } as Record<string, string>)[value] || value)
}
</script>

<style scoped>
.deck-canvas {
  --deck-bg:#F7FAFC;
  --deck-main:#2B6CB0;
  --deck-title:#1A365D;
  --deck-accent:#ED8936;
  --deck-body:#4A5568;
  --deck-chart:#E2E8F0;
  --deck-ink:var(--deck-title);
  --deck-muted:var(--deck-body);
  --deck-blue:var(--deck-main);
  --deck-blue-soft:#EBF8FF;
  --deck-teal:#087f74;
  --deck-teal-soft:#E2F7F0;
  --deck-amber:var(--deck-accent);
  --deck-amber-soft:#FFF0D9;
  --deck-red:#B54735;
  --deck-red-soft:#FFF1EE;
  --deck-paper:var(--deck-bg);
  --deck-card:#fff;
  --deck-line:var(--deck-chart);
  --deck-message-bg:#EBF8FF;
  --deck-callout:var(--deck-main);
  --deck-title-font:"Noto Sans SC","Microsoft YaHei","微软雅黑",sans-serif;
  --deck-body-font:"Noto Sans SC","Microsoft YaHei","微软雅黑",sans-serif;
  --deck-cover-wash:linear-gradient(155deg,var(--deck-title),var(--deck-main) 58%,var(--deck-accent));
  --deck-card-radius:1cqw;
  --deck-cover-image:none;
  --deck-chapter-image:none;
  --deck-recap-image:none;
  --deck-content-image:none;
  --deck-reasoning-image:none;
  --deck-practice-image:none;
  --deck-evidence-image:none;
  --deck-box-standard:var(--deck-card);
  --deck-box-standard-depth:var(--deck-line);
  --deck-box-message:var(--deck-blue-soft);
  --deck-box-message-depth:var(--deck-line);
  --deck-box-definition:var(--deck-card);
  --deck-box-definition-depth:var(--deck-line);
  --deck-box-boundary:var(--deck-teal-soft);
  --deck-box-boundary-depth:var(--deck-line);
  --deck-box-reasoning:var(--deck-blue-soft);
  --deck-box-reasoning-depth:var(--deck-line);
  --deck-box-practice:var(--deck-amber-soft);
  --deck-box-practice-depth:var(--deck-line);
  --deck-box-feedback:var(--deck-teal-soft);
  --deck-box-feedback-depth:var(--deck-line);
  --deck-box-misconception:var(--deck-red-soft);
  --deck-box-misconception-depth:var(--deck-line);
  --deck-box-evidence:var(--deck-title);
  --deck-box-evidence-depth:var(--deck-title);
  --deck-box-note:var(--deck-card);
  --deck-box-note-depth:var(--deck-line);
  position:relative;
  width:min(100%, 980px);
  aspect-ratio:16/9;
  overflow:hidden;
  color:var(--deck-ink);
  background:var(--deck-paper);
  box-shadow:0 28px 72px rgba(20,31,52,.18);
  container-type:inline-size;
  font-family:var(--deck-body-font);
}
.deck-canvas[data-theme="academic-bluegray"] {
  --deck-bg:#FCFCFD;
  --deck-title:#2C3E50;
  --deck-body:#5D6D7E;
  --deck-blue:#2E86C1;
  --deck-chart:#E8EBEE;
  --deck-main:var(--deck-blue);
  --deck-accent:var(--deck-blue);
  --deck-ink:var(--deck-title);
  --deck-muted:var(--deck-body);
  --deck-blue-soft:#F1F5F8;
  --deck-teal:#61768b;
  --deck-amber:#846947;
  --deck-paper:var(--deck-bg);
  --deck-card:#fff;
  --deck-line:var(--deck-chart);
  --deck-message-bg:#F3F6F8;
  --deck-callout:var(--deck-blue);
  --deck-title-font:"Noto Serif SC","SimSun","宋体",serif;
  --deck-body-font:"Noto Sans SC","Microsoft YaHei","微软雅黑",sans-serif;
  --deck-cover-wash:linear-gradient(155deg,var(--deck-title),#63778D 58%,#AAB3BD);
}
.deck-canvas[data-theme="qizhi-classroom"] {
  --deck-bg:#FFFDF7;
  --deck-title:#17365D;
  --deck-body:#34465C;
  --deck-main:#2F6FE4;
  --deck-accent:#F29D38;
  --deck-chart:#DCE9F7;
  --deck-blue-soft:#E7F0FF;
  --deck-teal:#16856B;
  --deck-paper:var(--deck-bg);
  --deck-card:#fff;
  --deck-line:#DDE5EE;
  --deck-message-bg:#EAF1FF;
  --deck-callout:#2F6FE4;
  --deck-cover-wash:linear-gradient(145deg,#17365D,#2F6FE4 60%,#F29D38);
}
.deck-canvas[data-template-rich="true"]:is(
  [data-layout="cover"],
  [data-layout="cover-minimal"],
  [data-layout="cover-editorial"]
) {
  background-color:var(--deck-paper);
  background-image:var(--deck-cover-image);
  background-repeat:no-repeat;
  background-position:center;
  background-size:cover;
}
.deck-canvas[data-template-rich="true"]:is(
  [data-layout="chapter"],
  [data-layout="chapter-entry"]
) {
  background-color:var(--deck-paper);
  background-image:var(--deck-chapter-image);
  background-repeat:no-repeat;
  background-position:center;
  background-size:cover;
}
.deck-canvas[data-template-rich="true"]:is(
  [data-layout="recap"],
  [data-layout="chapter-recap"],
  [data-layout="course-synthesis"]
) {
  background-color:var(--deck-paper);
  background-image:
    linear-gradient(rgba(255,253,247,.76),rgba(255,253,247,.76)),
    var(--deck-recap-image);
  background-repeat:no-repeat;
  background-position:center;
  background-size:cover;
}
.deck-canvas[data-template-rich="true"]:is(
  [data-layout="roadmap"],
  [data-layout="agenda-linear"],
  [data-layout="objective"],
  [data-layout="concept"],
  [data-layout="hero-statement"],
  [data-layout="hero-claim"],
  [data-layout="editorial-body"],
  [data-layout="balanced-two-column"],
  [data-layout="two-column"],
  [data-layout="classification-3"],
  [data-layout="parallel-examples"],
  [data-layout="case-study"],
  [data-layout="comparison"]
) {
  background-color:var(--deck-paper);
  background-image:var(--deck-content-image);
  background-repeat:no-repeat;
  background-position:center;
  background-size:cover;
}
.deck-canvas[data-template-rich="true"]:is(
  [data-layout="process"],
  [data-layout="process-sequence"],
  [data-layout="worked-example"],
  [data-layout="derivation-steps"],
  [data-layout="method-flow"],
  [data-layout="application-mapping"]
) {
  background-color:var(--deck-paper);
  background-image:var(--deck-reasoning-image);
  background-repeat:no-repeat;
  background-position:center;
  background-size:cover;
}
.deck-canvas[data-template-rich="true"]:is(
  [data-layout="practice"],
  [data-layout="question"],
  [data-layout="question-prompt"],
  [data-layout="practice-feedback"],
  [data-layout="misconception"],
  [data-layout="misconception-repair"]
) {
  background-color:var(--deck-paper);
  background-image:var(--deck-practice-image);
  background-repeat:no-repeat;
  background-position:center;
  background-size:cover;
}
.deck-canvas[data-template-rich="true"]:is(
  [data-layout="code"],
  [data-layout="formula"],
  [data-layout="formula-explanation"],
  [data-layout="figure-text"],
  [data-layout="diagram-full"],
  [data-layout="table-evidence"],
  [data-layout="code-focus"],
  [data-layout="formula-focus"]
) {
  background-color:var(--deck-paper);
  background-image:var(--deck-evidence-image);
  background-repeat:no-repeat;
  background-position:center;
  background-size:cover;
}
.deck-canvas[data-template-rich="true"] .deck-canvas__blocks > section {
  position:relative;
  border-radius:var(--deck-card-radius);
  border-color:color-mix(in srgb,var(--deck-line) 88%,#fff);
  background:color-mix(in srgb,var(--deck-box-standard) 96%,transparent);
  box-shadow:
    .32cqw .38cqw 0 var(--deck-box-standard-depth),
    0 .9cqw 2.2cqw rgba(23,54,93,.075),
    inset 0 .12cqw 0 rgba(255,255,255,.86);
}
.deck-canvas[data-template-rich="true"] .deck-canvas__blocks > section::before {
  content:"";
  position:absolute;
  inset:0 auto 0 0;
  width:.34cqw;
  background:var(--deck-blue);
}
.deck-canvas[data-template-rich="true"] .deck-canvas__blocks > section[data-type="comparison"] {
  background:color-mix(in srgb,var(--deck-box-boundary) 96%,transparent);
  box-shadow:.32cqw .38cqw 0 var(--deck-box-boundary-depth),0 .9cqw 2.2cqw rgba(23,54,93,.07),inset 0 .12cqw 0 rgba(255,255,255,.82);
}
.deck-canvas[data-template-rich="true"] .deck-canvas__blocks > section[data-type="comparison"]::before,
.deck-canvas[data-template-rich="true"] .deck-canvas__blocks > section[data-type="process"]::before {
  background:var(--deck-teal);
}
.deck-canvas[data-template-rich="true"] .deck-canvas__blocks > section[data-type="process"] {
  background:color-mix(in srgb,var(--deck-box-reasoning) 96%,transparent);
  box-shadow:.32cqw .38cqw 0 var(--deck-box-reasoning-depth),0 .9cqw 2.2cqw rgba(23,54,93,.07),inset 0 .12cqw 0 rgba(255,255,255,.82);
}
.deck-canvas[data-template-rich="true"] .deck-canvas__blocks > section[data-type="exercise"] {
  background:color-mix(in srgb,var(--deck-box-practice) 97%,transparent);
  box-shadow:.32cqw .38cqw 0 var(--deck-box-practice-depth),0 .9cqw 2.2cqw rgba(23,54,93,.07),inset 0 .12cqw 0 rgba(255,255,255,.82);
}
.deck-canvas[data-template-rich="true"] .deck-canvas__blocks > section[data-type="exercise"]::before {
  background:var(--deck-amber);
}
.deck-canvas[data-template-rich="true"] .deck-canvas__blocks > section[data-type="misconception"] {
  background:color-mix(in srgb,var(--deck-box-misconception) 97%,transparent);
  box-shadow:.32cqw .38cqw 0 var(--deck-box-misconception-depth),0 .9cqw 2.2cqw rgba(23,54,93,.07),inset 0 .12cqw 0 rgba(255,255,255,.82);
}
.deck-canvas[data-template-rich="true"] .deck-canvas__blocks > section[data-type="misconception"]::before {
  background:var(--deck-red);
}
.deck-canvas[data-template-rich="true"] .deck-canvas__blocks > section[data-type="callout"]::before,
.deck-canvas[data-template-rich="true"] .deck-canvas__blocks > section[data-type="code"]::before {
  display:none;
}
.deck-canvas[data-template-rich="true"] .deck-canvas__message {
  border:1px solid color-mix(in srgb,var(--deck-blue) 16%,var(--deck-line));
  border-left:.42cqw solid var(--deck-blue);
  border-radius:var(--deck-card-radius);
  background:linear-gradient(90deg,var(--deck-box-message),rgba(255,255,255,.68));
  box-shadow:.3cqw .34cqw 0 var(--deck-box-message-depth),0 .78cqw 1.9cqw rgba(23,54,93,.07),inset 0 .12cqw 0 rgba(255,255,255,.82);
}
.deck-canvas[data-theme="qizhi-classroom"] .deck-hero-claim {
  grid-template-columns:minmax(0,1fr);
}
.deck-canvas[data-theme="qizhi-classroom"] .deck-hero-claim > i {
  display:none;
}
.deck-canvas[data-template-rich="true"] .deck-hero-claim > i {
  display:none;
}
.deck-canvas[data-template-rich="true"] .deck-question-prompt,
.deck-canvas[data-template-rich="true"] .deck-hero-claim {
  padding:2.1cqw 2.4cqw;
  border:1px solid color-mix(in srgb,var(--deck-blue) 16%,var(--deck-line));
  border-left:.42cqw solid var(--deck-blue);
  border-radius:var(--deck-card-radius);
  background:color-mix(in srgb,var(--deck-box-message) 88%,rgba(255,255,255,.76));
  box-shadow:.34cqw .4cqw 0 var(--deck-box-message-depth),0 .95cqw 2.4cqw rgba(23,54,93,.075),inset 0 .12cqw 0 rgba(255,255,255,.84);
}
.deck-canvas[data-template-rich="true"] .deck-parallel-examples article,
.deck-canvas[data-template-rich="true"] .deck-classification__item {
  padding:1.25cqw 1.15cqw;
  border:1px solid var(--deck-line);
  border-top:.32cqw solid var(--deck-blue);
  border-radius:var(--deck-card-radius);
  background:color-mix(in srgb,var(--deck-box-definition) 94%,transparent);
  box-shadow:.28cqw .34cqw 0 var(--deck-box-definition-depth),0 .75cqw 1.9cqw rgba(23,54,93,.06),inset 0 .12cqw 0 rgba(255,255,255,.82);
}
.deck-canvas[data-template-rich="true"] .deck-worked-example article {
  margin:.18cqw 0;
  padding:.55cqw 1cqw;
  border:1px solid color-mix(in srgb,var(--deck-line) 84%,#fff);
  border-radius:var(--deck-card-radius);
  background:color-mix(in srgb,var(--deck-box-reasoning) 90%,transparent);
  box-shadow:.24cqw .28cqw 0 var(--deck-box-reasoning-depth),inset 0 .1cqw 0 rgba(255,255,255,.78);
}
.deck-canvas[data-template-rich="true"] .deck-practice-feedback__pair section,
.deck-canvas[data-template-rich="true"] .deck-practice-feedback__question {
  padding:1.1cqw 1.25cqw;
  border:1px solid color-mix(in srgb,var(--deck-blue) 15%,var(--deck-line));
  border-left:.34cqw solid var(--deck-blue);
  border-radius:var(--deck-card-radius);
  background:color-mix(in srgb,var(--deck-box-message) 94%,transparent);
  box-shadow:.26cqw .3cqw 0 var(--deck-box-message-depth),inset 0 .1cqw 0 rgba(255,255,255,.78);
}
.deck-canvas[data-template-rich="true"] .deck-practice-feedback__pair aside,
.deck-canvas[data-template-rich="true"] .deck-practice-feedback__evidence {
  padding:1.1cqw 1.25cqw;
  border:1px solid color-mix(in srgb,var(--deck-teal) 15%,var(--deck-line));
  border-left:.34cqw solid var(--deck-teal);
  border-radius:var(--deck-card-radius);
  background:color-mix(in srgb,var(--deck-box-feedback) 94%,transparent);
  box-shadow:.26cqw .3cqw 0 var(--deck-box-feedback-depth),inset 0 .1cqw 0 rgba(255,255,255,.78);
}
.deck-canvas[data-template-rich="true"] .deck-editorial-body__group {
  padding:1.05cqw 1.25cqw;
  border:1px solid var(--deck-line);
  border-left:.34cqw solid var(--deck-blue);
  border-radius:var(--deck-card-radius);
  background:color-mix(in srgb,var(--deck-box-note) 92%,transparent);
  box-shadow:.26cqw .3cqw 0 var(--deck-box-note-depth),inset 0 .1cqw 0 rgba(255,255,255,.78);
}
.deck-canvas[data-theme="academic-editorial"] {
  --deck-bg:#FBFAF7;
  --deck-title:#273340;
  --deck-body:#45515D;
  --deck-main:#315E7D;
  --deck-accent:#8B6B3E;
  --deck-chart:#E1E2DF;
  --deck-blue-soft:#E8ECEC;
  --deck-teal:#4F6D64;
  --deck-paper:var(--deck-bg);
  --deck-card:#FFFEFB;
  --deck-line:#D8D8D3;
  --deck-message-bg:#ECEDE9;
  --deck-callout:#315E7D;
  --deck-title-font:"Noto Serif SC","SimSun","宋体",serif;
  --deck-cover-wash:linear-gradient(145deg,#273340,#526575 64%,#B2A58D);
}
.deck-canvas[data-theme="grid-notebook"] {
  --deck-bg:#FAF8F0;
  --deck-title:#283B36;
  --deck-body:#40524D;
  --deck-main:#2D7464;
  --deck-accent:#D18A32;
  --deck-chart:#DDE5DE;
  --deck-blue-soft:#E1ECE5;
  --deck-teal:#648B57;
  --deck-paper:var(--deck-bg);
  --deck-card:rgba(255,255,252,.9);
  --deck-line:#D5DED7;
  --deck-message-bg:#E7EFE9;
  --deck-callout:#2D7464;
  --deck-cover-wash:linear-gradient(145deg,#283B36,#2D7464 62%,#D18A32);
  background-image:linear-gradient(rgba(45,116,100,.075) 1px,transparent 1px),linear-gradient(90deg,rgba(45,116,100,.075) 1px,transparent 1px);
  background-size:3.2cqw 3.2cqw;
}
.deck-canvas[data-theme="modern-geometric"] {
  --deck-bg:#F6F3FF;
  --deck-title:#231A4A;
  --deck-body:#463D62;
  --deck-main:#6548E8;
  --deck-accent:#F08B3E;
  --deck-chart:#DDD5F2;
  --deck-blue-soft:#E6DFFF;
  --deck-teal:#138D85;
  --deck-paper:var(--deck-bg);
  --deck-card:#fff;
  --deck-line:#D8D0EC;
  --deck-message-bg:#E8E1FF;
  --deck-callout:#6548E8;
  --deck-cover-wash:linear-gradient(135deg,#231A4A,#6548E8 58%,#F08B3E);
}
.deck-canvas[data-theme="modern-geometric"]::before {
  content:"";
  position:absolute;
  right:-7%;
  top:-12%;
  width:31%;
  aspect-ratio:1;
  border-radius:25% 52% 30% 55%;
  background:color-mix(in srgb,var(--deck-accent) 18%,transparent);
  transform:rotate(27deg);
}
.deck-canvas[data-theme="dark-tech"] {
  --deck-bg:#0C1321;
  --deck-title:#F3F8FF;
  --deck-body:#D7E3F2;
  --deck-main:#4DB5FF;
  --deck-accent:#40D6B1;
  --deck-chart:#22334B;
  --deck-ink:var(--deck-title);
  --deck-muted:#91A6BE;
  --deck-blue:#4DB5FF;
  --deck-blue-soft:#183C5A;
  --deck-teal:#40D6B1;
  --deck-amber:#FFB35A;
  --deck-paper:var(--deck-bg);
  --deck-card:#121E30;
  --deck-line:#29405C;
  --deck-message-bg:#142D43;
  --deck-callout:#4DB5FF;
  --deck-cover-wash:linear-gradient(145deg,#050912,#123150 62%,#166B68);
}
.deck-canvas[data-theme="dark-tech"] .deck-canvas__blocks > section {
  box-shadow:inset 0 0 0 1px rgba(77,181,255,.14),0 0 28px rgba(22,96,135,.08);
}
.deck-canvas[data-layout="editorial-body"] .deck-canvas__blocks { grid-template-columns:1fr; }
.deck-canvas:is([data-layout="two-column"],[data-layout="balanced-two-column"]) .deck-canvas__blocks { grid-template-columns:repeat(2,minmax(0,1fr)); }
.deck-canvas[data-layout="concept-cards"] .deck-canvas__blocks { grid-template-columns:repeat(3,minmax(0,1fr)); }
.deck-canvas[data-layout="classification-3"] .deck-canvas__blocks { grid-template-columns:1fr; }
.deck-canvas[data-layout="classification-3"] .deck-canvas__blocks > section {
  padding:0;
  border:0;
  border-radius:0;
  background:transparent;
}
.deck-classification {
  display:grid;
  height:100%;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:2.4cqw;
}
.deck-classification__item {
  min-width:0;
  padding:1.5cqw 1.2cqw;
  border-top:.32cqw solid var(--deck-blue);
  border-bottom:1px solid var(--deck-line);
}
.deck-classification__item > b {
  display:block;
  margin-bottom:1.2cqw;
  color:var(--deck-blue);
  font:800 1.05cqw/1 "Aptos Mono","SFMono-Regular",monospace;
}
.deck-classification__item :deep(.markdown-body) {
  color:var(--deck-ink);
  font-size:1.6cqw;
  line-height:1.46;
}
.deck-parallel-examples,
.deck-question-prompt,
.deck-worked-example,
.deck-practice-feedback,
.deck-chapter-recap,
.deck-course-synthesis {
  position:absolute;
  inset:25% 5.5% 10.5%;
  min-height:0;
}
.deck-parallel-examples[data-has-message="true"],
.deck-question-prompt[data-has-message="true"],
.deck-worked-example[data-has-message="true"],
.deck-practice-feedback[data-has-message="true"],
.deck-chapter-recap[data-has-message="true"],
.deck-course-synthesis[data-has-message="true"] { top:38%; }
.deck-parallel-examples {
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(0,1fr));
  gap:1.8cqw;
  align-items:stretch;
}
.deck-parallel-examples article {
  min-width:0;
  padding:1.25cqw 0;
  border-top:.32cqw solid var(--deck-blue);
  border-bottom:1px solid var(--deck-line);
}
.deck-parallel-examples article > b {
  display:block;
  margin-bottom:1.15cqw;
  color:var(--deck-blue);
  font:800 .92cqw/1 "Aptos Mono","SFMono-Regular",monospace;
}
.deck-parallel-examples article :deep(.markdown-body) {
  font-size:1.65cqw;
  font-weight:700;
  line-height:1.45;
}
.deck-question-prompt {
  display:flex;
  flex-direction:column;
  justify-content:center;
  padding-left:2.3cqw;
  border-left:.42cqw solid var(--deck-blue);
}
.deck-question-prompt > small {
  margin-bottom:1.35cqw;
  color:var(--deck-blue);
  font-size:1.02cqw;
  font-weight:800;
  letter-spacing:.12em;
}
.deck-question-prompt :deep(.markdown-body) {
  max-width:78cqw;
  font-family:var(--deck-title-font);
  font-size:2.05cqw;
  font-weight:700;
  line-height:1.48;
}
.deck-question-prompt__items {
  display:grid;
  gap:1.2cqw;
}
.deck-question-prompt__items > :deep(.markdown-body) + :deep(.markdown-body) {
  padding-top:1cqw;
  border-top:1px solid var(--deck-line);
}
.deck-worked-example {
  display:grid;
  grid-template-rows:repeat(3,minmax(0,1fr));
}
.deck-worked-example::before {
  content:"";
  position:absolute;
  left:1.2cqw;
  top:1.4cqw;
  bottom:1.4cqw;
  width:1px;
  background:var(--deck-line);
}
.deck-worked-example article {
  position:relative;
  display:grid;
  grid-template-columns:2.4cqw 4.2cqw 1fr;
  align-items:center;
  gap:1.1cqw;
  min-height:0;
  border-bottom:1px solid var(--deck-line);
}
.deck-worked-example article:last-child { border-bottom:0; }
.deck-worked-example article > b {
  z-index:1;
  display:grid;
  width:2.25cqw;
  height:2.25cqw;
  place-items:center;
  border-radius:50%;
  color:#fff;
  background:var(--deck-blue);
  font:800 .9cqw/1 "Aptos Mono","SFMono-Regular",monospace;
}
.deck-worked-example article > small {
  color:var(--deck-blue);
  font-size:1.05cqw;
  font-weight:800;
  letter-spacing:.1em;
}
.deck-worked-example article :deep(.markdown-body) {
  font-size:1.6cqw;
  font-weight:680;
  line-height:1.42;
}
.deck-practice-feedback {
  display:grid;
  grid-auto-rows:minmax(0,1fr);
  gap:1.2cqw;
  align-content:start;
}
.deck-practice-feedback[data-feedback-mode="shared_evidence"] {
  grid-template-rows:auto minmax(0,1fr);
  gap:1.35cqw;
}
.deck-practice-feedback__questions {
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(0,1fr));
  gap:2.2cqw;
  padding:.45cqw 0 1.35cqw;
  border-bottom:1px solid var(--deck-line);
}
.deck-practice-feedback__question {
  min-width:0;
  padding-left:1.5cqw;
  border-left:.34cqw solid var(--deck-blue);
}
.deck-practice-feedback__question :deep(.markdown-body) {
  font-size:1.55cqw;
  font-weight:700;
  line-height:1.46;
}
.deck-practice-feedback__evidence {
  min-width:0;
  padding:1.05cqw 0 0 1.5cqw;
  border-left:.34cqw solid var(--deck-teal);
}
.deck-practice-feedback__evidence ul {
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(0,1fr));
  gap:1.15cqw 2.2cqw;
  margin:0;
  padding:0;
  list-style:none;
}
.deck-practice-feedback__evidence li {
  min-width:0;
  padding-top:.65cqw;
  border-top:1px solid var(--deck-line);
}
.deck-practice-feedback__evidence li :deep(.markdown-body) {
  font-size:1.43cqw;
  line-height:1.44;
}
.deck-practice-feedback__pair {
  display:grid;
  grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);
  gap:2.6cqw;
  min-height:0;
  padding:1.1cqw 0 1.25cqw;
  border-bottom:1px solid var(--deck-line);
}
.deck-practice-feedback__pair:first-child { padding-top:.4cqw; }
.deck-practice-feedback__pair:last-child { border-bottom:0; }
.deck-practice-feedback__pair section,
.deck-practice-feedback__pair aside {
  min-width:0;
  padding-left:1.5cqw;
  border-left:.34cqw solid var(--deck-blue);
}
.deck-practice-feedback__pair aside {
  border-left:1px solid var(--deck-line);
}
.deck-practice-feedback small {
  display:block;
  margin-bottom:.8cqw;
  color:var(--deck-blue);
  font-size:.96cqw;
  font-weight:800;
  letter-spacing:.08em;
}
.deck-practice-feedback__pair section :deep(.markdown-body) {
  font-size:1.58cqw;
  font-weight:700;
  line-height:1.46;
}
.deck-practice-feedback__pair aside :deep(.markdown-body) {
  font-size:1.48cqw;
  line-height:1.45;
}
.deck-chapter-recap {
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:1.55cqw 2.2cqw;
  align-items:start;
  padding-top:1.9cqw;
  border-top:1px solid var(--deck-line);
}
.deck-chapter-recap article {
  position:relative;
  min-width:0;
  padding-top:1.3cqw;
}
.deck-chapter-recap article::before {
  content:"";
  position:absolute;
  top:-2.15cqw;
  left:0;
  width:.72cqw;
  height:.72cqw;
  border-radius:50%;
  background:var(--deck-blue);
}
.deck-chapter-recap article > b {
  display:block;
  margin-bottom:.9cqw;
  color:var(--deck-blue);
  font:800 .92cqw/1 "Aptos Mono","SFMono-Regular",monospace;
}
.deck-chapter-recap article :deep(.markdown-body) {
  font-size:1.6cqw;
  font-weight:700;
  line-height:1.44;
}
.deck-course-synthesis {
  display:grid;
  grid-template-columns:minmax(0,.72fr) minmax(0,1.48fr);
  gap:3.4cqw;
}
.deck-course-synthesis > aside {
  padding-right:2.2cqw;
  border-right:1px solid var(--deck-line);
}
.deck-course-synthesis > aside small {
  display:block;
  margin-bottom:1.2cqw;
  color:var(--deck-blue);
  font-size:1.05cqw;
  font-weight:800;
  letter-spacing:.1em;
}
.deck-course-synthesis > aside strong {
  display:block;
  font:750 2cqw/1.34 var(--deck-title-font);
}
.deck-course-synthesis > ol {
  display:grid;
  gap:.45cqw;
  margin:0;
  padding:0;
  list-style:none;
}
.deck-course-synthesis > ol li {
  display:grid;
  grid-template-columns:2.4cqw 1fr;
  align-items:center;
  min-height:0;
  border-bottom:1px solid var(--deck-line);
}
.deck-course-synthesis > ol li > b {
  color:var(--deck-blue);
  font:800 .9cqw/1 "Aptos Mono","SFMono-Regular",monospace;
}
.deck-course-synthesis > ol li :deep(.markdown-body) {
  font-size:1.6cqw;
  font-weight:700;
  line-height:1.35;
}
.deck-canvas[data-layout="hero-statement"] .deck-canvas__blocks section {
  display:flex;
  align-items:center;
  padding:6% 8%;
  border:0;
  border-left:.55cqw solid var(--deck-blue);
  background:var(--deck-blue-soft);
}
.deck-canvas[data-layout="hero-statement"] .deck-canvas__blocks p {
  font-family:var(--deck-title-font);
  font-size:2.15cqw;
  font-weight:700;
  line-height:1.42;
}
.deck-canvas[data-layout="case-study"] .deck-canvas__blocks {
  padding-left:25%;
  background:linear-gradient(90deg,var(--deck-blue-soft) 0 22%,transparent 22%);
}
.deck-canvas[data-layout="case-study"] .deck-canvas__blocks section {
  border-left:.48cqw solid var(--deck-teal);
}
.deck-canvas[data-layout="question"] .deck-canvas__blocks section {
  border-color:color-mix(in srgb,var(--deck-amber) 38%,var(--deck-line));
  background:color-mix(in srgb,var(--deck-amber) 8%,var(--deck-card));
}
.deck-canvas[data-layout="appendix"] .deck-canvas__heading small { color:var(--deck-amber); }
.deck-canvas[data-layout="formula"] .deck-canvas__blocks p { font-family:"Times New Roman",serif; font-size:1.8cqw; }
.deck-canvas::after {
  content:"";
  position:absolute;
  inset:0;
  pointer-events:none;
  box-shadow:inset 0 0 0 1px rgba(23,32,44,.08);
}
.deck-canvas h2,.deck-canvas blockquote,.deck-canvas p { margin:0; }
.deck-canvas > footer {
  position:absolute;
  inset:auto 5.5% 3.4%;
  z-index:3;
  display:flex;
  justify-content:space-between;
  color:#8d98a8;
  font:650 .78cqw/1 "Aptos Mono","SFMono-Regular",monospace;
  letter-spacing:.04em;
}
.deck-canvas__heading {
  position:absolute;
  inset:7.3% 5.5% auto;
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:4%;
  padding-bottom:2.2%;
  border-bottom:1px solid var(--deck-line);
}
.deck-canvas__heading > div { min-width:0; }
.deck-canvas__heading small {
  color:var(--deck-blue);
  font-size:1.02cqw;
  font-weight:800;
  letter-spacing:.18em;
  text-transform:uppercase;
}
.deck-canvas__heading h2 {
  margin-top:.7%;
  max-width:78cqw;
  font-family:var(--deck-title-font);
  font-size:3.55cqw;
  font-weight:700;
  line-height:1.16;
  letter-spacing:-.025em;
}
.deck-canvas__heading > span {
  color:#aeb7c4;
  font:750 1.1cqw/1 "Aptos Mono","SFMono-Regular",monospace;
}
.deck-canvas[data-heading-mode="hidden"] .deck-canvas__heading {
  padding-bottom:1.35%;
}
.deck-canvas[data-heading-mode="hidden"] .deck-canvas__heading small {
  font-size:1.12cqw;
}
.deck-canvas__message {
  position:absolute;
  inset:25.5% 5.5% auto;
  min-height:8.7%;
  padding:1.35% 1.8%;
  border-left:.42cqw solid var(--deck-blue);
  color:var(--deck-ink);
  background:var(--deck-message-bg);
  font-size:1.6cqw;
  font-weight:720;
  line-height:1.42;
}
.deck-canvas[data-heading-mode="hidden"] .deck-canvas__message { top:16.5%; }
.deck-hero-claim {
  position:absolute;
  inset:27% 8% 12%;
  display:grid;
  grid-template-columns:.48cqw minmax(0,1fr);
  align-items:center;
  gap:3.2cqw;
}
.deck-hero-claim > i {
  width:.48cqw;
  height:72%;
  background:var(--deck-blue);
}
.deck-hero-claim > strong {
  max-width:76cqw;
  color:var(--deck-ink);
  font:750 2.7cqw/1.42 var(--deck-title-font);
}
.deck-canvas__story {
  position:absolute;
  inset:25% 5.5% 10.5%;
  display:grid;
  grid-template-columns:minmax(0,1.18fr) minmax(0,.82fr);
  gap:2.4%;
  min-height:0;
}
.deck-canvas__story[data-has-message="true"] { top:38%; }
.deck-canvas__story[data-composition="split-visual"] {
  grid-template-columns:minmax(0,.92fr) minmax(0,1.08fr);
}
.deck-canvas__story[data-composition="split-visual"] > .slide-visual { order:2; }
.deck-canvas__story[data-composition="split-visual"] > .deck-canvas__source { order:1; }
.deck-canvas__story[data-composition="diagram-full"] {
  grid-template-columns:minmax(0,1.35fr) minmax(0,.65fr);
}
.deck-canvas__story[data-composition="exercise"] {
  grid-template-columns:minmax(0,.78fr) minmax(0,1.22fr);
}
.deck-canvas__story[data-density="dense"] {
  grid-template-columns:minmax(0,.78fr) minmax(0,1.22fr);
}
.deck-canvas__story[data-density="dense"] > .slide-visual { order:2; }
.deck-canvas__story[data-density="dense"] > .deck-canvas__source { order:1; }
.deck-canvas__story[data-source-empty="true"] {
  grid-template-columns:minmax(0,1fr);
}
.deck-canvas__story[data-layout-variant="table-with-interpretation"] {
  grid-template-columns:minmax(0,1.35fr) minmax(0,.65fr);
}
.deck-canvas__story[data-layout-variant="table-with-interpretation"] > .slide-visual { order:1; }
.deck-canvas__story[data-layout-variant="table-with-interpretation"] > .deck-canvas__source { order:2; }
.deck-canvas__source {
  min-width:0;
  overflow:hidden;
  padding:1.3cqw 0 1cqw 1.6cqw;
  border-left:.34cqw solid var(--deck-blue);
}
.deck-canvas__source > small {
  display:block;
  margin-bottom:1cqw;
  color:var(--deck-blue);
  font-size:1.05cqw;
  font-weight:800;
  letter-spacing:.08em;
}
.deck-canvas__source section {
  margin:0 0 .9cqw;
  padding:0;
  border:0;
  background:transparent;
}
.deck-canvas__source section > b {
  display:block;
  margin-bottom:.4cqw;
  font-size:1.35cqw;
}
.deck-canvas__source p,.deck-canvas__source li {
  color:var(--deck-body);
  font-size:1.68cqw;
  line-height:1.38;
}
.deck-canvas__source ul,.deck-canvas__source ol {
  display:grid;
  gap:.52cqw;
  margin:0;
  padding-left:1.25cqw;
}
.deck-canvas__source ol {
  list-style:none;
  padding-left:0;
}
.deck-canvas__source ol li {
  display:flex;
  gap:.7cqw;
}
.deck-canvas__source ol i {
  display:grid;
  width:1.55cqw;
  height:1.55cqw;
  flex:0 0 auto;
  place-items:center;
  border-radius:50%;
  color:#fff;
  background:var(--deck-blue);
  font-style:normal;
  font-size:.82cqw;
  font-weight:800;
}
.deck-canvas__source pre {
  max-height:13.5cqw;
  overflow:hidden;
  white-space:pre-wrap;
  font-size:1.68cqw;
  line-height:1.42;
}
.deck-canvas__blocks {
  position:absolute;
  inset:25% 5.5% 10.5%;
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(0,1fr));
  gap:1.8%;
}
.deck-canvas__navigation {
  position:absolute;
  inset:31% 8% 18%;
  display:grid;
  grid-template-columns:.8cqw 1fr;
  grid-template-rows:auto 1fr auto;
  column-gap:2.2cqw;
  align-items:start;
}
.deck-canvas__navigation > i {
  grid-row:1/4;
  width:.42cqw;
  height:100%;
  background:var(--deck-blue);
}
.deck-canvas__navigation > small {
  color:var(--deck-blue);
  font-size:1.05cqw;
  font-weight:800;
  letter-spacing:.08em;
}
.deck-canvas__navigation > strong {
  align-self:center;
  color:var(--deck-title);
  font:800 2.4cqw/1.32 var(--deck-title-font);
}
.deck-canvas__navigation > p {
  margin:0;
  color:var(--deck-muted);
  font-size:1.6cqw;
  font-weight:650;
}
.deck-inline-markdown :deep(.markdown-body) {
  margin:0;
  color:inherit;
  font:inherit;
}
.deck-inline-markdown :deep(.katex-display) {
  margin:.45em 0;
  overflow:visible;
}
.deck-editorial-body {
  position:absolute;
  inset:27% 8% 10.5%;
  display:grid;
  align-content:center;
  gap:1.8cqw;
  min-height:0;
  padding-left:2.5cqw;
  border-left:.34cqw solid var(--deck-blue);
}
.deck-editorial-body[data-has-message="true"] { top:39%; }
.deck-editorial-body__group {
  min-width:0;
  overflow:hidden;
  padding:0 0 1.25cqw;
  border:0;
  border-bottom:1px solid var(--deck-line);
  border-radius:0;
  background:transparent;
}
.deck-editorial-body__group:last-child {
  padding-bottom:0;
  border-bottom:0;
}
.deck-editorial-body__group > small {
  display:block;
  margin-bottom:.75cqw;
  color:var(--deck-blue);
  font-size:1.05cqw;
  font-weight:800;
  letter-spacing:.06em;
}
.deck-editorial-body__group :deep(.markdown-body),
.deck-editorial-body__group li {
  color:var(--deck-ink);
  font-size:1.62cqw;
  line-height:1.5;
}
.deck-editorial-body__group ul {
  display:grid;
  gap:.65cqw;
  margin:0;
  padding-left:0;
  list-style:none;
}
.deck-canvas[data-heading-mode="hidden"] .deck-editorial-body { top:18%; }
.deck-canvas[data-heading-mode="hidden"] .deck-editorial-body[data-has-message="true"] { top:30%; }
.deck-canvas__blocks[data-has-message="true"] { top:38%; }
.deck-canvas__blocks[data-layout="objective"],
.deck-canvas__blocks[data-layout="objective-cards"] { inset:25% 5.5% 10.5%; grid-template-columns:1.05fr 1fr 1fr; }
.deck-canvas__blocks[data-layout="code"] { inset:25% 5.5% 10.5%; grid-template-columns:1.75fr 1fr; }
.deck-canvas__blocks[data-layout="practice"],
.deck-canvas__blocks[data-layout="question"],
.deck-canvas__blocks[data-layout="misconception"] { inset:25% 5.5% 10.5%; grid-template-columns:1.55fr .9fr; }
.deck-canvas__blocks[data-layout="roadmap"],
.deck-canvas__blocks[data-layout="process"] { inset:28% 5.5% 11%; }
.deck-canvas__blocks[data-layout="comparison"] { inset:26% 5.5% 10.5%; }
.deck-canvas__blocks[data-layout="appendix"] {
  inset:25% 5.5% 10.5%;
  grid-template-columns:1fr;
}
.deck-canvas__blocks[data-layout="appendix"] section {
  padding:3.1%;
  border-left:.42cqw solid var(--deck-blue);
}
.deck-canvas__blocks[data-layout="appendix"] p {
  white-space:pre-line;
  font-size:1.6cqw;
  line-height:1.58;
}
.deck-canvas__blocks[data-layout="appendix"][data-count="1"] p {
  column-count:2;
  column-gap:3.2cqw;
  column-rule:1px solid var(--deck-line);
}
.deck-canvas__blocks[data-count="1"]:not([data-layout="appendix"]) p {
  font-size:1.72cqw;
  line-height:1.48;
}
.deck-canvas__blocks[data-count="1"]:not([data-layout="appendix"]) li {
  font-size:1.6cqw;
}
.deck-canvas__blocks:is([data-layout="recap"],[data-layout="summary"])[data-count="1"] ul {
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:1.1cqw 2.4cqw;
  padding-left:1.4em;
}
.deck-canvas__blocks section {
  min-width:0;
  overflow:hidden;
  padding:7%;
  border:1px solid var(--deck-line);
  border-radius:1.15cqw;
  background:var(--deck-card);
}
.deck-canvas__blocks section > header {
  display:flex;
  align-items:center;
  gap:7%;
  margin-bottom:7%;
}
.deck-canvas__blocks section > header b {
  color:#a1acba;
  font:750 .74cqw/1 "Aptos Mono","SFMono-Regular",monospace;
}
.deck-canvas__blocks section > header span {
  color:var(--deck-blue);
  font-size:1.08cqw;
  font-weight:800;
}
.deck-canvas__blocks p,.deck-canvas__blocks li {
  margin:0;
  color:var(--deck-ink);
  font-size:1.6cqw;
  line-height:1.52;
}
.deck-canvas__blocks ul { display:grid; gap:.55em; margin:0; padding-left:1.25em; }
.deck-canvas__blocks ul li::marker { color:var(--deck-blue); }
.deck-canvas__blocks ol { display:grid; gap:7%; margin:0; padding:0; list-style:none; }
.deck-canvas__blocks ol li { display:flex; gap:6%; align-items:flex-start; }
.deck-canvas__blocks ol b {
  width:2.05em;
  height:2.05em;
  flex:none;
  display:grid;
  place-items:center;
  border-radius:50%;
  color:#fff;
  background:var(--deck-blue);
  font-size:.88em;
}
.deck-canvas[data-layout="process-sequence"][data-task-prompt-mode="action"] .deck-canvas__blocks {
  inset:25% 5.5% 10.5%;
  grid-template-columns:1fr;
}
.deck-canvas[data-layout="process-sequence"][data-task-prompt-mode="action"] .deck-canvas__blocks section {
  padding:2.5% 3%;
  border:0;
  border-radius:0;
  background:transparent;
}
.deck-canvas[data-layout="process-sequence"][data-task-prompt-mode="action"] .deck-canvas__blocks ol {
  height:100%;
  gap:0;
}
.deck-canvas[data-layout="process-sequence"][data-task-prompt-mode="action"] .deck-canvas__blocks ol li {
  display:grid;
  grid-template-columns:3.2cqw minmax(0,1fr);
  align-items:center;
  gap:1.5cqw;
  min-height:0;
  padding:.8cqw 0;
  border-bottom:1px solid var(--deck-line);
}
.deck-canvas[data-layout="process-sequence"][data-task-prompt-mode="action"] .deck-canvas__blocks ol li:last-child {
  border-bottom:0;
}
.deck-canvas__blocks pre {
  height:100%;
  margin:0;
  overflow:hidden;
  white-space:pre-wrap;
}
.deck-canvas__blocks section[data-type="code"] { padding:5%; border-color:#17202c; color:#ecf1f8; background:#17202c; }
.deck-canvas__blocks code { color:#f5f7fb; font:1.02cqw/1.5 "Aptos Mono","SFMono-Regular",monospace; }
.deck-canvas__blocks section[data-type="misconception"] { border-color:#f1c8c0; background:#fff4f1; }
.deck-canvas__blocks section[data-type="misconception"] > header span { color:#b54735; }
.deck-canvas__blocks section[data-type="exercise"] { border-color:#ead5b5; background:#fff9ed; }
.deck-canvas__blocks section[data-type="exercise"] > header span { color:var(--deck-amber); }
.deck-canvas__blocks section[data-type="callout"] { color:#fff; border-color:var(--deck-callout); background:var(--deck-callout); }
.deck-canvas__blocks section[data-type="callout"] p,
.deck-canvas__blocks section[data-type="callout"] li,
.deck-canvas__blocks section[data-type="callout"] > header span { color:#fff; }
.deck-canvas table { width:100%; border-collapse:collapse; font-size:1.6cqw; }
.deck-canvas th,.deck-canvas td { padding:.55em .65em; border-bottom:1px solid var(--deck-line); text-align:left; }
.deck-canvas th { color:var(--deck-blue); background:var(--deck-blue-soft); }
.deck-cover__wash {
  position:absolute;
  inset:0 0 0 auto;
  width:31%;
  background:
    radial-gradient(circle at 72% 26%,rgba(255,255,255,.24) 0 1.2%,transparent 1.4%),
    var(--deck-cover-wash);
}
.deck-cover__wash::before {
  content:"";
  position:absolute;
  inset:14% 18%;
  border:1px solid rgba(255,255,255,.28);
  transform:rotate(8deg);
}
.deck-canvas[data-theme="qizhi-classroom"] .deck-cover__wash { display:none; }
.deck-cover__index {
  position:absolute;
  inset:8% auto auto 6%;
  color:#b0bac8;
  font:750 1cqw/1 "Aptos Mono","SFMono-Regular",monospace;
}
.deck-cover__brand {
  position:absolute;
  inset:8% 6% auto auto;
  z-index:2;
  color:#fff;
  font-size:1.18cqw;
  font-weight:800;
  letter-spacing:.16em;
}
.deck-cover__content { position:absolute; inset:17% 35% 13% 6%; }
.deck-cover__content small {
  color:var(--deck-blue);
  font-size:1.16cqw;
  font-weight:800;
  letter-spacing:.16em;
}
.deck-cover__content h2 {
  margin-top:5%;
  font-family:var(--deck-title-font);
  font-size:4.35cqw;
  line-height:1.12;
  letter-spacing:-.035em;
}
.deck-cover__content p { margin-top:4%; color:var(--deck-muted); font-size:1.6cqw; }
.deck-cover__content blockquote {
  margin-top:7%;
  padding:3% 3.5%;
  border-left:.35cqw solid var(--deck-teal);
  color:#2c3746;
  background:var(--deck-message-bg);
  font-size:1.6cqw;
  font-weight:700;
  line-height:1.45;
}
.deck-canvas[data-layout="cover-minimal"] .deck-cover__content {
  inset:18% 8% 16%;
  display:flex;
  flex-direction:column;
  justify-content:center;
}
.deck-canvas[data-theme="qizhi-classroom"][data-layout="cover-minimal"] .deck-cover__content {
  inset:18% 38% 16% 6%;
}
.deck-claim-only {
  position:absolute;
  inset:31% 8% 17%;
  display:grid;
  grid-template-columns:.7cqw 1fr;
  grid-template-rows:auto 1fr;
  column-gap:2cqw;
}
.deck-claim-only > i {
  grid-row:1/3;
  width:.38cqw;
  height:100%;
  background:var(--deck-blue);
}
.deck-claim-only > small {
  color:var(--deck-blue);
  font-size:1.08cqw;
  font-weight:800;
  letter-spacing:.08em;
}
.deck-canvas[data-layout="cover-minimal"] .deck-cover__content::before {
  content:"";
  width:4.8cqw;
  height:.32cqw;
  margin-bottom:2.2cqw;
  background:var(--deck-blue);
}
.deck-canvas[data-layout="cover-minimal"] .deck-cover__content h2 {
  max-width:84cqw;
  font-size:5.1cqw;
  line-height:1.08;
}
.deck-canvas[data-layout="cover-minimal"] .deck-cover__content p {
  max-width:68cqw;
  margin-top:2.4cqw;
}
.deck-canvas[data-layout="agenda-linear"] .deck-canvas__blocks {
  inset:25% 7% 11%;
  grid-template-columns:1fr;
}
.deck-canvas[data-layout="agenda-linear"] .deck-canvas__blocks > section {
  padding:0;
  border:0;
  border-radius:0;
  background:transparent;
}
.deck-canvas[data-layout="agenda-linear"] .deck-canvas__blocks ol {
  height:100%;
  gap:0;
}
.deck-canvas[data-layout="agenda-linear"] .deck-canvas__blocks ol li {
  display:grid;
  grid-template-columns:3.4cqw 1fr;
  align-items:center;
  padding:.72cqw 0;
  border-bottom:1px solid var(--deck-line);
}
.deck-canvas[data-layout="agenda-linear"] .deck-canvas__blocks ol b {
  width:auto;
  height:auto;
  border-radius:0;
  color:var(--deck-blue);
  background:transparent;
  font:800 1cqw/1 "Aptos Mono","SFMono-Regular",monospace;
}
.deck-chapter__panel {
  position:absolute;
  inset:0 auto 0 0;
  width:34%;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  color:#fff;
  background:var(--deck-cover-wash);
}
.deck-chapter__panel small { font-size:.9cqw; font-weight:800; letter-spacing:.28em; opacity:.75; }
.deck-chapter__panel strong { margin-top:8%; font:800 7.8cqw/1 "Aptos Mono","SFMono-Regular",monospace; }
.deck-canvas[data-theme="qizhi-classroom"] .deck-chapter__panel { background:transparent; }
.deck-chapter__content { position:absolute; inset:21% 7% 15% 40%; }
.deck-chapter__content small { color:var(--deck-teal); font-size:1.12cqw; font-weight:800; letter-spacing:.16em; }
.deck-chapter__content h2 {
  margin-top:5%;
  font-family:var(--deck-title-font);
  font-size:3.55cqw;
  line-height:1.18;
}
.deck-chapter__content i { display:block; width:12%; height:.34cqw; margin-top:6%; background:var(--deck-blue); }
.deck-chapter__content blockquote { margin-top:7%; color:var(--deck-muted); font-size:1.6cqw; font-weight:650; line-height:1.48; }
.deck-canvas.is-presenting { width:min(92vw, 166vh); max-height:88vh; box-shadow:0 32px 96px rgba(0,0,0,.4); }
</style>
