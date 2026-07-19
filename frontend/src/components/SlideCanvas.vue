<template>
  <article
    class="deck-canvas"
    :class="{ 'is-presenting': presenting }"
    :data-layout="slide.layout"
    :data-theme="theme"
    :aria-label="`${pageNumber} / ${pageCount} · ${slide.title}`"
  >
    <template v-if="slide.layout === 'cover'">
      <div class="deck-cover__wash"></div>
      <div class="deck-cover__index">{{ String(pageNumber).padStart(2, '0') }}</div>
      <div class="deck-cover__brand">{{ t('teachingRepresentations.slides.brand', '灵知') }}</div>
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
        <blockquote>{{ slide.key_message }}</blockquote>
      </div>
      <footer><span>{{ deckTitle }}</span><span>{{ pageNumber }} / {{ pageCount }}</span></footer>
    </template>

    <template v-else>
      <header class="deck-canvas__heading">
        <div>
          <small>{{ slide.eyebrow || layoutLabel(slide.layout) }}</small>
          <h2>{{ slide.title }}</h2>
        </div>
        <span>{{ String(pageNumber).padStart(2, '0') }}</span>
      </header>

      <blockquote
        v-if="slide.key_message && !['objective', 'misconception', 'practice'].includes(slide.layout)"
        class="deck-canvas__message"
      >
        {{ slide.key_message }}
      </blockquote>

      <div class="deck-canvas__blocks" :data-layout="slide.layout" :data-count="slide.blocks?.length || 0">
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
              <b>{{ itemIndex + 1 }}</b><span>{{ item }}</span>
            </li>
          </ol>
          <ul v-else-if="block.items?.length">
            <li v-for="item in block.items" :key="item">{{ item }}</li>
          </ul>
          <p v-else>{{ block.content }}</p>
        </section>
      </div>

      <footer>
        <span>{{ slide.section_id || deckTitle }}</span>
        <span>{{ pageNumber }} / {{ pageCount }}</span>
      </footer>
    </template>
  </article>
</template>

<script setup lang="ts">
import { t } from '../shared/i18n'
import type { SlideDeckTheme } from '../stores/teachingRepresentations'

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
  section_id?: string
  blocks: SlideBlock[]
}

withDefaults(defineProps<{
  slide: Slide
  pageNumber: number
  pageCount: number
  deckTitle: string
  theme?: SlideDeckTheme
  presenting?: boolean
}>(), {
  theme: 'qingfeng-classroom',
  presenting: false,
})

function chapterNumber(title: string) {
  return title.match(/\d+/)?.[0]?.padStart(2, '0') || '·'
}

function layoutLabel(value: string) {
  return t(`teachingRepresentations.slides.layouts.${value}`, ({
    cover: '封面',
    roadmap: '路线',
    chapter: '章节',
    objective: '目标',
    concept: '概念',
    comparison: '对比',
    process: '过程',
    code: '代码',
    misconception: '易错',
    practice: '练习',
    recap: '小结',
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
.deck-canvas__blocks {
  position:absolute;
  inset:38% 5.5% 10.5%;
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(0,1fr));
  gap:1.8%;
}
.deck-canvas__blocks[data-layout="objective"] { inset:25% 5.5% 10.5%; grid-template-columns:1.05fr 1fr 1fr; }
.deck-canvas__blocks[data-layout="code"] { inset:25% 5.5% 10.5%; grid-template-columns:1.75fr 1fr; }
.deck-canvas__blocks[data-layout="practice"],
.deck-canvas__blocks[data-layout="misconception"] { inset:25% 5.5% 10.5%; grid-template-columns:1.55fr .9fr; }
.deck-canvas__blocks[data-layout="roadmap"],
.deck-canvas__blocks[data-layout="process"] { inset:28% 5.5% 11%; }
.deck-canvas__blocks[data-layout="comparison"] { inset:26% 5.5% 10.5%; }
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
