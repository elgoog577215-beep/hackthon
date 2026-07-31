<template>
  <article
    class="deck-canvas"
    :class="{ 'is-presenting': presenting }"
    :data-layout="visualLayout"
    :data-layout-contract="v5LayoutNames.has(visualLayout) ? layoutContract.schema_version : undefined"
    :data-theme="theme"
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
          <small>{{ slide.eyebrow || layoutLabel(visualLayout) }}</small>
          <h2>{{ displayHeading }}</h2>
        </div>
        <span>{{ String(pageNumber).padStart(2, '0') }}</span>
      </header>

      <blockquote
        v-if="slide.key_message && !['objective', 'misconception', 'practice'].includes(slide.layout)"
        class="deck-canvas__message"
      >
        {{ slide.key_message }}
      </blockquote>

      <div
        v-if="slide.visuals?.length"
        class="deck-canvas__story"
        :data-composition="resolvedComposition"
        :data-source-empty="sourceBlocks.length === 0"
        :data-density="sourceCharacterCount > 180 ? 'dense' : 'normal'"
      >
        <SlideVisualRenderer
          :visuals="slide.visuals"
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
        v-else-if="slide.quality?.suppress_redundant_body"
        class="deck-claim-only"
      >
        <i></i>
        <small>{{ slide.teaching_job || slide.eyebrow || '核心判断' }}</small>
      </div>

      <div
        v-else-if="visualLayout === 'worked-example'"
        class="deck-worked-example"
        :data-has-message="Boolean(slide.key_message)"
      >
        <article v-for="(item, index) in semanticItems.slice(0, 3)" :key="`${index}-${item}`">
          <b>{{ index + 1 }}</b>
          <small>{{ workedStepLabel(index, Math.min(3, semanticItems.length)) }}</small>
          <MarkdownRenderer :content="item" :enable-code-run="false" />
        </article>
      </div>

      <div
        v-else-if="visualLayout === 'practice-feedback'"
        class="deck-practice-feedback"
        :data-has-message="Boolean(slide.key_message)"
      >
        <section>
          <small>先独立作答</small>
          <MarkdownRenderer :content="semanticItems[0] || slide.key_message || ''" :enable-code-run="false" />
        </section>
        <aside>
          <small>反馈依据</small>
          <ol>
            <li v-for="item in semanticItems.slice(1, 5)" :key="item">
              <MarkdownRenderer :content="item" :enable-code-run="false" />
            </li>
          </ol>
        </aside>
      </div>

      <div
        v-else-if="visualLayout === 'chapter-recap'"
        class="deck-chapter-recap"
        :data-has-message="Boolean(slide.key_message)"
      >
        <article v-for="(item, index) in semanticItems.slice(0, 5)" :key="`${index}-${item}`">
          <b>{{ String(index + 1).padStart(2, '0') }}</b>
          <MarkdownRenderer :content="item" :enable-code-run="false" />
        </article>
      </div>

      <div
        v-else-if="visualLayout === 'course-synthesis'"
        class="deck-course-synthesis"
        :data-has-message="Boolean(slide.key_message)"
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
        v-else-if="slide.blocks?.length"
        class="deck-canvas__blocks"
        :data-layout="visualLayout"
        :data-count="slide.blocks?.length || 0"
        :data-has-message="Boolean(slide.key_message)"
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
  }
}

const props = withDefaults(defineProps<{
  slide: Slide
  pageNumber: number
  pageCount: number
  deckTitle: string
  theme?: SlideDeckTheme
  presenting?: boolean
  courseId?: string
  representationId?: string
}>(), {
  theme: 'qingfeng-classroom',
  presenting: false,
  courseId: '',
  representationId: '',
})

const visualLayout = computed(() => (
  props.slide.quality?.resolved_layout
  || props.slide.quality?.requested_layout
  || props.slide.layout
))
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
  if (visualKind !== 'formula') return props.slide.blocks || []
  return (props.slide.blocks || []).filter(
    block => block.type !== 'formula' && !block.metadata?.formula,
  )
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
function headingExcerpt(value: string, limit = 48) {
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
  return headingExcerpt(props.slide.title, 46)
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
const themeStyle = computed(() => {
  const aliases: Record<string, string> = {
    'qingfeng-classroom': 'qizhi-classroom',
    'academic-bluegray': 'academic-editorial',
  }
  const key = aliases[props.theme] || props.theme
  const token = (themePack.themes as Record<string, Record<string, any>>)[key]
  if (!token) return {}
  return {
    '--deck-bg': `#${token.surface}`,
    '--deck-paper': `#${token.surface}`,
    '--deck-title': `#${token.title}`,
    '--deck-ink': `#${token.title}`,
    '--deck-body': `#${token.ink}`,
    '--deck-muted': `#${token.muted}`,
    '--deck-main': `#${token.accent}`,
    '--deck-blue': `#${token.accent}`,
    '--deck-blue-soft': `#${token.accent_soft}`,
    '--deck-teal': `#${token.green}`,
    '--deck-amber': `#${token.amber}`,
    '--deck-card': `#${token.surface}`,
    '--deck-line': `#${token.chart_bg}`,
    '--deck-message-bg': `#${token.accent_soft}`,
    '--deck-callout': `#${token.accent}`,
    '--deck-title-font': `"${token.title_font}","${token.title_east_asian_font}",sans-serif`,
    '--deck-body-font': `"${token.body_font}","${token.body_east_asian_font}",sans-serif`,
  }
})

function chapterNumber(title: string) {
  return title.match(/\d+/)?.[0]?.padStart(2, '0') || '·'
}

function workedStepLabel(index: number, total: number) {
  return total >= 3
    ? ['已知', '推理', '结论'][index]
    : ['情境', '判断'][index]
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
  --deck-amber:var(--deck-accent);
  --deck-paper:var(--deck-bg);
  --deck-card:#fff;
  --deck-line:var(--deck-chart);
  --deck-message-bg:#EBF8FF;
  --deck-callout:var(--deck-main);
  --deck-title-font:"Noto Sans SC","Microsoft YaHei","微软雅黑",sans-serif;
  --deck-body-font:"Noto Sans SC","Microsoft YaHei","微软雅黑",sans-serif;
  --deck-cover-wash:linear-gradient(155deg,var(--deck-title),var(--deck-main) 58%,var(--deck-accent));
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
  font-size:1.55cqw;
  line-height:1.46;
}
.deck-worked-example,
.deck-practice-feedback,
.deck-chapter-recap,
.deck-course-synthesis {
  position:absolute;
  inset:25% 5.5% 10.5%;
  min-height:0;
}
.deck-worked-example[data-has-message="true"],
.deck-practice-feedback[data-has-message="true"],
.deck-chapter-recap[data-has-message="true"],
.deck-course-synthesis[data-has-message="true"] { top:38%; }
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
  font-size:1.5cqw;
  font-weight:680;
  line-height:1.42;
}
.deck-practice-feedback {
  display:grid;
  grid-template-columns:minmax(0,1.8fr) minmax(0,.9fr);
  gap:3cqw;
}
.deck-practice-feedback section,
.deck-practice-feedback aside {
  min-width:0;
  padding:1cqw 0 1cqw 1.6cqw;
  border-left:.34cqw solid var(--deck-blue);
}
.deck-practice-feedback aside {
  border-left:1px solid var(--deck-line);
}
.deck-practice-feedback small {
  display:block;
  margin-bottom:1.2cqw;
  color:var(--deck-blue);
  font-size:1.05cqw;
  font-weight:800;
  letter-spacing:.08em;
}
.deck-practice-feedback section :deep(.markdown-body) {
  font-size:1.72cqw;
  font-weight:700;
  line-height:1.5;
}
.deck-practice-feedback ol {
  display:grid;
  gap:1cqw;
  margin:0;
  padding-left:1.25em;
}
.deck-practice-feedback aside :deep(.markdown-body) {
  font-size:1.42cqw;
  line-height:1.45;
}
.deck-chapter-recap {
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(0,1fr));
  gap:1.3cqw;
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
  font-size:1.42cqw;
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
  font-size:1.4cqw;
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
  font-size:2.72cqw;
  font-weight:700;
  line-height:1.16;
  letter-spacing:-.025em;
}
.deck-canvas__heading > span {
  color:#aeb7c4;
  font:750 1.1cqw/1 "Aptos Mono","SFMono-Regular",monospace;
}
.deck-canvas__message {
  position:absolute;
  inset:25.5% 5.5% auto;
  min-height:8.7%;
  padding:1.35% 1.8%;
  border-left:.42cqw solid var(--deck-blue);
  color:var(--deck-ink);
  background:var(--deck-message-bg);
  font-size:1.36cqw;
  font-weight:720;
  line-height:1.42;
}
.deck-canvas__story {
  position:absolute;
  inset:25% 5.5% 10.5%;
  display:grid;
  grid-template-columns:minmax(0,1.18fr) minmax(0,.82fr);
  gap:2.4%;
  min-height:0;
}
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
  font-size:1.18cqw;
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
  font-size:1.42cqw;
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
  font-size:1.48cqw;
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
  font-size:1.18cqw;
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
.deck-canvas table { width:100%; border-collapse:collapse; font-size:1cqw; }
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
.deck-cover__content p { margin-top:4%; color:var(--deck-muted); font-size:1.48cqw; }
.deck-cover__content blockquote {
  margin-top:7%;
  padding:3% 3.5%;
  border-left:.35cqw solid var(--deck-teal);
  color:#2c3746;
  background:var(--deck-message-bg);
  font-size:1.42cqw;
  font-weight:700;
  line-height:1.45;
}
.deck-canvas[data-layout="cover-minimal"] .deck-cover__content {
  inset:18% 8% 16%;
  display:flex;
  flex-direction:column;
  justify-content:center;
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
.deck-chapter__content { position:absolute; inset:21% 7% 15% 40%; }
.deck-chapter__content small { color:var(--deck-teal); font-size:1.12cqw; font-weight:800; letter-spacing:.16em; }
.deck-chapter__content h2 {
  margin-top:5%;
  font-family:var(--deck-title-font);
  font-size:3.55cqw;
  line-height:1.18;
}
.deck-chapter__content i { display:block; width:12%; height:.34cqw; margin-top:6%; background:var(--deck-blue); }
.deck-chapter__content blockquote { margin-top:7%; color:var(--deck-muted); font-size:1.48cqw; font-weight:650; line-height:1.48; }
.deck-canvas.is-presenting { width:min(92vw, 166vh); max-height:88vh; box-shadow:0 32px 96px rgba(0,0,0,.4); }
</style>
