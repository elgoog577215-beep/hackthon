<template>
  <div v-if="open" class="deck-generator" role="dialog" aria-modal="true" aria-labelledby="deck-generator-title">
    <div class="deck-generator__panel">
      <header>
        <div>
          <small>PPT GENERATOR</small>
          <h2 id="deck-generator-title">{{ manuscriptFirst ? t('pptWorkspace.generateManuscript', '生成页面内容稿') : '生成课程课件' }}</h2>
          <p>{{ manuscriptFirst ? t('pptWorkspace.manuscriptDialogDescription', '先生成逐页页面内容稿，确认后再生成可编辑 PPT。') : '课程正文将原样进入课件，AI 只负责分页、排版与审核。' }}</p>
        </div>
        <button v-if="closable" type="button" aria-label="关闭" @click="emit('close')"><X :size="18" /></button>
      </header>

      <section>
        <div class="deck-generator__section-title">
          <div><span>01</span><strong>选择内容模式</strong></div>
          <small>{{ pageEstimate }}</small>
        </div>
        <div class="deck-generator__modes">
          <button
            v-for="item in modes"
            :key="item.value"
            type="button"
            :class="{ active: modelMode === item.value }"
            @click="modelMode = item.value"
          >
            <span><component :is="item.icon" :size="19" /></span>
            <strong>{{ item.label }}</strong>
            <small>{{ item.description }}</small>
            <i>{{ item.coverage }}</i>
          </button>
        </div>
      </section>

      <section>
        <div class="deck-generator__section-title">
          <div><span>02</span><strong>选择视觉风格</strong></div>
          <small>切换风格会重新排版并单独缓存</small>
        </div>
        <div class="deck-generator__theme-tabs" role="tablist">
          <button
            type="button"
            data-testid="builtin-template-tab"
            :class="{ active: templateTab === 'builtin' }"
            @click="templateTab = 'builtin'"
          >{{ t('pptTemplatePacks.builtinTab', '内置模板') }}</button>
          <button
            v-if="personalTemplatesEnabled"
            type="button"
            data-testid="personal-template-tab"
            :class="{ active: templateTab === 'personal' }"
            @click="templateTab = 'personal'; emit('load-templates')"
          >{{ t('pptTemplatePacks.personalTab', '我的模板') }}</button>
        </div>
        <div v-if="templateTab === 'builtin'" class="deck-generator__themes">
          <button
            v-for="item in themes"
            :key="item.value"
            type="button"
            :data-theme="item.value"
            :class="{ active: modelTheme === item.value }"
            @click="selectBuiltinTheme(item.value)"
          >
            <div class="deck-theme-preview-real">
              <SlideCanvas
                v-for="(slide, previewIndex) in previewSlides"
                :key="slide.unit_id"
                :slide="slide"
                :page-number="previewIndex + 1"
                :page-count="previewSlides.length"
                deck-title="线性映射"
                :theme="item.value"
              />
            </div>
            <strong>{{ item.label }}</strong>
            <small>{{ item.description }}</small>
          </button>
        </div>
        <div v-else-if="personalTemplatesEnabled" class="deck-generator__personal-templates">
          <button
            type="button"
            class="deck-generator__create-template"
            data-testid="create-template-pack"
            @click="emit('create-template')"
          >
            <span>+</span>
            <strong>{{ t('pptTemplatePacks.create', '创建模板') }}</strong>
            <small>{{ t('pptTemplatePacks.createHint', '上传参考 PPTX，或填写品牌颜色和 Logo') }}</small>
          </button>
          <button
            v-for="item in personalTemplates"
            :key="item.pack_id"
            type="button"
            :data-template-pack-id="item.pack_id"
            :class="{ active: selectedTemplatePack?.pack_id === item.pack_id }"
            :disabled="!item.latest_version || !item.v6_eligible"
            @click="selectPersonalTemplate(item)"
          >
            <span>{{ item.name.slice(0, 1) }}</span>
            <strong>{{ item.name }}</strong>
            <small>{{ item.latest_version ? `v${item.latest_version}` : t('pptTemplatePacks.draft', '草稿') }}</small>
          </button>
          <p v-if="!personalTemplates.length" class="deck-generator__personal-empty">
            {{ t('pptTemplatePacks.empty', '还没有个人模板；上传一份参考 PPTX 即可开始。') }}
          </p>
        </div>
      </section>

      <section>
        <div class="deck-generator__section-title">
          <div><span>03</span><strong>联网教学图片</strong></div>
          <small>可选；默认关闭</small>
        </div>
        <label class="deck-generator__web-images">
          <input
            v-model="modelWebImageRetrieval"
            data-testid="ppt-web-image-retrieval"
            type="checkbox"
            :disabled="busy"
          />
          <span>
            <strong>检索可授权复用的教学图片</strong>
            <small>仅使用公共领域、CC0 或 CC BY 图片；没有安全匹配时继续使用可编辑图示。</small>
          </span>
        </label>
      </section>

      <footer>
        <div>
          <ShieldCheck :size="16" />
          <span>原文哈希校验 · 失败不覆盖旧版本 · PPTX 保持可编辑</span>
        </div>
        <button type="button" :disabled="busy" @click="confirm">
          <LoaderCircle v-if="busy" :size="17" class="spinning" />
          <Sparkles v-else :size="17" />
          {{ busy ? t('pptWorkspace.generatingManuscript', '正在生成页面内容稿…') : manuscriptFirst ? t('pptWorkspace.generateManuscript', '生成页面内容稿') : '开始生成课件' }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { BookOpenText, Layers3, LoaderCircle, Presentation, ShieldCheck, Sparkles, X } from 'lucide-vue-next'
import type { SlideDeckMode, SlideDeckTheme } from '../stores/teachingRepresentations'
import SlideCanvas from './SlideCanvas.vue'
import { t } from '../shared/i18n'

type V3Theme = Exclude<SlideDeckTheme, 'qingfeng-classroom' | 'academic-bluegray'>

export interface PersonalPptTemplatePack {
  pack_id: string
  name: string
  base_theme: V3Theme
  status: 'draft' | 'published'
  latest_version: number
  v6_eligible?: boolean
  preview?: Record<string, unknown>
}

const props = withDefaults(defineProps<{
  open: boolean
  mode?: SlideDeckMode
  theme?: V3Theme
  busy?: boolean
  closable?: boolean
  fragmentCount?: number
  durationMinutes?: number
  webImageRetrieval?: boolean
  personalTemplates?: PersonalPptTemplatePack[]
  personalTemplatesEnabled?: boolean
  manuscriptFirst?: boolean
}>(), {
  mode: 'teaching',
  theme: 'academic-editorial',
  busy: false,
  closable: true,
  fragmentCount: 0,
  durationMinutes: 0,
  webImageRetrieval: false,
  personalTemplates: () => [],
  personalTemplatesEnabled: true,
  manuscriptFirst: false,
})

watch(() => props.personalTemplatesEnabled, enabled => {
  if (!enabled && templateTab.value === 'personal') {
    templateTab.value = 'builtin'
    selectedTemplatePack.value = null
  }
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'confirm', value: {
    mode: SlideDeckMode
    theme: V3Theme
    webImageRetrieval: { enabled: boolean; mode: 'wide_safe' }
    templatePackId?: string
    templatePackVersion?: number
  }): void
  (event: 'create-template'): void
  (event: 'load-templates'): void
}>()

const modelMode = ref<SlideDeckMode>(props.mode)
const modelTheme = ref<V3Theme>(props.theme)
const modelWebImageRetrieval = ref(props.webImageRetrieval)
const templateTab = ref<'builtin' | 'personal'>('builtin')
const selectedTemplatePack = ref<PersonalPptTemplatePack | null>(null)

watch(() => props.open, open => {
  if (!open) return
  modelMode.value = props.mode
  modelTheme.value = props.theme
  modelWebImageRetrieval.value = props.webImageRetrieval
  templateTab.value = 'builtin'
  selectedTemplatePack.value = null
})

const modes = [
  { value: 'full' as const, label: '完整课件', description: '全部正文进入教学主线', coverage: '主线 100% 覆盖', icon: Layers3 },
  { value: 'teaching' as const, label: '授课课件', description: '核心主线 + 原文附录', coverage: '整份 100% 覆盖', icon: Presentation },
  { value: 'concise' as const, label: '精简课件', description: '核心内容与明确排除清单', coverage: '适合快速讲解', icon: BookOpenText },
]

const themes: Array<{ value: V3Theme; label: string; description: string }> = [
  { value: 'qizhi-classroom', label: '启智课堂', description: '明亮亲和 · 通用教学' },
  { value: 'academic-editorial', label: '学术编辑', description: '严谨克制 · 理论课程' },
  { value: 'grid-notebook', label: '网格笔记', description: '批注高亮 · 知识整理' },
  { value: 'modern-geometric', label: '现代几何', description: '大色块 · 公开课' },
  { value: 'dark-tech', label: '深色科技', description: '深色高亮 · 编程科技' },
]

const previewSlides = [
  {
    unit_id: 'theme-preview-cover',
    layout: 'cover',
    slide_purpose: 'orientation',
    eyebrow: '课程演示',
    title: '线性映射',
    subtitle: '定义、方法与应用',
    key_message: '',
    blocks: [],
  },
  {
    unit_id: 'theme-preview-concept',
    layout: 'concept',
    slide_purpose: 'concept',
    eyebrow: '核心概念',
    title: '线性映射保持两种运算',
    blocks: [{
      block_id: 'theme-preview-concept-body',
      type: 'statement',
      content: '同时保持向量加法与数乘。',
      items: [],
    }],
    quality: { requested_layout: 'hero-statement' },
  },
  {
    unit_id: 'theme-preview-example',
    layout: 'concept',
    slide_purpose: 'example',
    eyebrow: '完整例题',
    title: '先判断，再验证',
    blocks: [{
      block_id: 'theme-preview-example-body',
      type: 'process',
      content: '',
      items: ['识别目标', '验证加法', '验证数乘'],
    }],
    quality: { requested_layout: 'case-study' },
  },
  {
    unit_id: 'theme-preview-recap',
    layout: 'recap',
    slide_purpose: 'chapter_recap',
    eyebrow: '章节总结',
    title: '回到学习目标',
    blocks: [{
      block_id: 'theme-preview-recap-body',
      type: 'bullets',
      content: '',
      items: ['理解定义', '掌握判断', '完成检查'],
    }],
  },
] as any[]

const pageEstimate = computed(() => {
  if (props.manuscriptFirst && props.durationMinutes > 0) {
    const duration = props.durationMinutes
    if (modelMode.value === 'full') {
      const center = Math.max(8, Math.round(duration / 2.8) + 2)
      return `预计 ${Math.max(6, center - 3)}–${center + 5} 页`
    }
    if (modelMode.value === 'teaching') {
      const center = Math.max(7, Math.round(duration / 3.5) + 2)
      return `预计 ${Math.max(6, center - 3)}–${center + 3} 页`
    }
    const center = Math.max(6, Math.round(duration / 5) + 2)
    return `预计 ${Math.max(5, center - 3)}–${center + 3} 页`
  }
  const base = Math.max(6, Math.ceil(props.fragmentCount / 3) + 3)
  if (modelMode.value === 'full') return `预计 ${base}–${base + 5} 页`
  if (modelMode.value === 'teaching') return `预计 ${Math.max(6, base - 2)}–${base + 2} 页`
  return `预计 ${Math.max(5, Math.round(base * .55))}–${Math.max(7, Math.round(base * .72))} 页`
})

function selectBuiltinTheme(theme: V3Theme) {
  modelTheme.value = theme
  selectedTemplatePack.value = null
}

function selectPersonalTemplate(template: PersonalPptTemplatePack) {
  if (!template.latest_version || !template.v6_eligible) return
  selectedTemplatePack.value = template
  modelTheme.value = template.base_theme
}

function confirm() {
  const value: {
    mode: SlideDeckMode
    theme: V3Theme
    webImageRetrieval: { enabled: boolean; mode: 'wide_safe' }
    templatePackId?: string
    templatePackVersion?: number
  } = {
    mode: modelMode.value,
    theme: modelTheme.value,
    webImageRetrieval: {
      enabled: modelWebImageRetrieval.value,
      mode: 'wide_safe',
    },
  }
  if (selectedTemplatePack.value) {
    value.templatePackId = selectedTemplatePack.value.pack_id
    value.templatePackVersion = selectedTemplatePack.value.latest_version
  }
  emit('confirm', value)
}
</script>

<style scoped>
.deck-generator { position:fixed; inset:52px 0 0; z-index:120; display:grid; place-items:center; padding:28px; color:#182433; background:rgba(17,25,38,.72); backdrop-filter:blur(18px); }
.deck-generator__panel { width:min(1050px,100%); max-height:calc(100vh - 104px); overflow:auto; border:1px solid rgba(255,255,255,.72); border-radius:24px; background:#f8fafc; box-shadow:0 30px 90px rgba(4,12,26,.34); }
.deck-generator__panel > header { display:flex; align-items:flex-start; justify-content:space-between; gap:24px; padding:30px 34px 24px; border-bottom:1px solid #e3e9f0; background:linear-gradient(135deg,#fff,#f2f6fc); }
.deck-generator__panel > header small { color:#3265d9; font-size:11px; font-weight:850; letter-spacing:.18em; }
.deck-generator__panel > header h2 { margin:8px 0 6px; font-size:28px; letter-spacing:-.03em; }
.deck-generator__panel > header p { margin:0; color:#667487; font-size:14px; }
.deck-generator__panel > header button { width:34px; height:34px; display:grid; place-items:center; border:1px solid #dae1ea; border-radius:10px; color:#536276; background:#fff; }
.deck-generator__panel > section { padding:25px 34px 0; }
.deck-generator__section-title { display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }
.deck-generator__section-title > div { display:flex; align-items:center; gap:10px; }
.deck-generator__section-title span { color:#3265d9; font:800 11px/1 "Aptos Mono",monospace; }
.deck-generator__section-title strong { font-size:15px; }
.deck-generator__section-title > small { color:#7b8797; font-size:12px; }
.deck-generator__modes { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
.deck-generator__modes button { position:relative; min-height:126px; display:grid; grid-template-columns:auto 1fr; grid-template-rows:auto auto 1fr; gap:4px 12px; padding:18px; text-align:left; border:1px solid #dce3eb; border-radius:16px; color:#263448; background:#fff; transition:.18s ease; }
.deck-generator__modes button:hover,.deck-generator__modes button.active { border-color:#6c91ec; box-shadow:0 10px 26px rgba(42,76,141,.1); transform:translateY(-1px); }
.deck-generator__modes button.active { box-shadow:inset 0 0 0 1px #4d78df,0 10px 26px rgba(42,76,141,.11); }
.deck-generator__modes button > span { grid-row:1/4; width:38px; height:38px; display:grid; place-items:center; border-radius:11px; color:#2f62d8; background:#eaf0ff; }
.deck-generator__modes strong { font-size:15px; }
.deck-generator__modes small { color:#738094; font-size:12px; line-height:1.45; }
.deck-generator__modes i { align-self:end; color:#2f62d8; font-size:11px; font-style:normal; font-weight:750; }
.deck-generator__themes { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; }
.deck-generator__theme-tabs { width:max-content; display:flex; gap:4px; margin:0 0 12px; padding:4px; border-radius:11px; background:#e9eef5; }
.deck-generator__theme-tabs button { min-height:32px; padding:0 15px; border:0; border-radius:8px; color:#69788c; background:transparent; font-size:12px; font-weight:750; }
.deck-generator__theme-tabs button.active { color:#214fae; background:#fff; box-shadow:0 3px 10px rgba(34,62,105,.1); }
.deck-generator__personal-templates { position:relative; display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; min-height:112px; }
.deck-generator__personal-templates > button { min-height:106px; display:grid; grid-template-columns:38px minmax(0,1fr); align-content:center; gap:4px 10px; padding:14px; text-align:left; border:1px solid #dce3eb; border-radius:15px; color:#263448; background:#fff; }
.deck-generator__personal-templates > button:hover,.deck-generator__personal-templates > button.active { border-color:#6c91ec; box-shadow:inset 0 0 0 1px #4d78df,0 9px 24px rgba(42,76,141,.1); }
.deck-generator__personal-templates > button:disabled { opacity:.58; cursor:not-allowed; }
.deck-generator__personal-templates > button > span { grid-row:1/3; width:38px; height:38px; display:grid; place-items:center; border-radius:11px; color:#315fca; background:#eaf0ff; font-weight:850; }
.deck-generator__personal-templates > button > strong { align-self:end; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; }
.deck-generator__personal-templates > button > small { color:#7b8797; font-size:10px; }
.deck-generator__personal-templates .deck-generator__create-template { border-style:dashed; }
.deck-generator__personal-empty { position:absolute; left:25%; right:0; top:36px; margin:0; color:#7b8797; text-align:center; font-size:12px; pointer-events:none; }
.deck-generator__themes > button { padding:8px 8px 12px; text-align:left; border:1px solid #dce3eb; border-radius:15px; color:#263448; background:#fff; transition:.18s ease; }
.deck-generator__themes > button:hover,.deck-generator__themes > button.active { border-color:#6c91ec; box-shadow:0 9px 24px rgba(42,76,141,.1); transform:translateY(-1px); }
.deck-generator__themes > button.active { box-shadow:inset 0 0 0 1px #4d78df,0 9px 24px rgba(42,76,141,.11); }
.deck-theme-preview-real { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:3px; padding:4px; overflow:hidden; border-radius:9px; background:#dfe5ee; }
.deck-theme-preview-real :deep(.deck-canvas) { width:100%; box-shadow:none; pointer-events:none; }
.deck-generator__themes strong,.deck-generator__themes small { display:block; padding:0 4px; }
.deck-generator__themes strong { margin-top:9px; font-size:13px; }
.deck-generator__themes small { margin-top:3px; color:#7a8797; font-size:10px; }
.deck-generator__web-images { display:flex; align-items:flex-start; gap:12px; padding:16px 18px; border:1px solid #dce3eb; border-radius:15px; background:#fff; cursor:pointer; }
.deck-generator__web-images input { width:18px; height:18px; margin:2px 0 0; accent-color:#2f63da; }
.deck-generator__web-images span { display:grid; gap:4px; }
.deck-generator__web-images strong { color:#263448; font-size:14px; }
.deck-generator__web-images small { color:#738094; font-size:12px; line-height:1.5; }
.deck-theme-preview { position:relative; aspect-ratio:16/9; display:grid; grid-template-columns:1.18fr .82fr; grid-template-rows:1fr 1fr; gap:3px; padding:4px; overflow:hidden; border-radius:9px; color:var(--i); background:color-mix(in srgb,var(--p) 84%,var(--s)); box-shadow:inset 0 0 0 1px rgba(20,30,45,.08); }
.deck-theme-preview > div { position:relative; overflow:hidden; border-radius:4px; background:var(--p); box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--m) 13%,transparent); }
.deck-theme-preview__cover { grid-row:1/3; padding:10px 7px; }
.deck-theme-preview__cover i { display:block; width:4px; height:72%; border-radius:3px; background:var(--m); }
.deck-theme-preview__cover b,.deck-theme-preview__cover span { position:absolute; left:17px; display:block; }
.deck-theme-preview__cover b { top:19px; max-width:62px; font-size:8px; line-height:1.1; }
.deck-theme-preview__cover span { top:39px; color:color-mix(in srgb,var(--i) 68%,transparent); font-size:5px; }
.deck-theme-preview__split { padding:6px; }
.deck-theme-preview__split b { font-size:5px; }
.deck-theme-preview__split i,.deck-theme-preview__split span { position:absolute; bottom:7px; height:16px; border-radius:3px; }
.deck-theme-preview__split i { left:6px; width:31%; background:var(--s); }
.deck-theme-preview__split span { right:6px; width:47%; background:color-mix(in srgb,var(--a) 28%,var(--p)); }
.deck-theme-preview__split em { position:absolute; right:10px; bottom:11px; width:25%; height:2px; background:var(--a); transform:rotate(-18deg); }
.deck-theme-preview__diagram { display:flex; align-items:center; justify-content:center; gap:4px; }
.deck-theme-preview__diagram i { min-width:22px; padding:4px 3px; border:1px solid var(--m); border-radius:4px; color:var(--i); background:var(--s); font-size:4px; font-style:normal; text-align:center; }
.deck-theme-preview__diagram b { width:13px; height:1px; background:var(--m); }
button[data-theme="grid-notebook"] .deck-theme-preview { background-image:linear-gradient(color-mix(in srgb,var(--m) 12%,transparent) 1px,transparent 1px),linear-gradient(90deg,color-mix(in srgb,var(--m) 12%,transparent) 1px,transparent 1px); background-size:9px 9px; }
.deck-generator__panel > footer { display:flex; align-items:center; justify-content:space-between; gap:20px; margin-top:26px; padding:21px 34px 26px; border-top:1px solid #e3e9f0; }
.deck-generator__panel > footer > div { display:flex; align-items:center; gap:8px; color:#6c7a8d; font-size:12px; }
.deck-generator__panel > footer > div svg { color:#16856b; }
.deck-generator__panel > footer > button { min-height:43px; display:flex; align-items:center; gap:8px; padding:0 22px; border:0; border-radius:12px; color:#fff; background:#2f63da; box-shadow:0 9px 22px rgba(47,99,218,.24); font-weight:750; }
.deck-generator__panel > footer > button:disabled { opacity:.7; }
.spinning { animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:900px) {
  .deck-generator { padding:14px; }
  .deck-generator__modes { grid-template-columns:1fr; }
  .deck-generator__themes { grid-template-columns:repeat(2,1fr); }
  .deck-generator__personal-templates { grid-template-columns:repeat(2,1fr); }
  .deck-generator__panel > footer { align-items:flex-start; flex-direction:column; }
}
</style>
