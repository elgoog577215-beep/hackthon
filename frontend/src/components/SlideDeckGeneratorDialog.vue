<template>
  <div v-if="open" class="deck-generator" role="dialog" aria-modal="true" aria-labelledby="deck-generator-title">
    <div class="deck-generator__panel">
      <header>
        <div>
          <small>PPT GENERATOR</small>
          <h2 id="deck-generator-title">生成课程课件</h2>
          <p>课程正文将原样进入课件，AI 只负责分页、排版与审核。</p>
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
        <div class="deck-generator__themes">
          <button
            v-for="item in themes"
            :key="item.value"
            type="button"
            :data-theme="item.value"
            :class="{ active: modelTheme === item.value }"
            @click="modelTheme = item.value"
          >
            <div class="deck-theme-preview">
              <i></i><b></b><span></span><em></em>
            </div>
            <strong>{{ item.label }}</strong>
            <small>{{ item.description }}</small>
          </button>
        </div>
      </section>

      <footer>
        <div>
          <ShieldCheck :size="16" />
          <span>原文哈希校验 · 失败不覆盖旧版本 · PPTX 保持可编辑</span>
        </div>
        <button type="button" :disabled="busy" @click="confirm">
          <LoaderCircle v-if="busy" :size="17" class="spinning" />
          <Sparkles v-else :size="17" />
          {{ busy ? '正在生成…' : '开始生成课件' }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { BookOpenText, Layers3, LoaderCircle, Presentation, ShieldCheck, Sparkles, X } from 'lucide-vue-next'
import type { SlideDeckMode, SlideDeckTheme } from '../stores/teachingRepresentations'

type V3Theme = Exclude<SlideDeckTheme, 'qingfeng-classroom' | 'academic-bluegray'>

const props = withDefaults(defineProps<{
  open: boolean
  mode?: SlideDeckMode
  theme?: V3Theme
  busy?: boolean
  closable?: boolean
  fragmentCount?: number
}>(), {
  mode: 'teaching',
  theme: 'qizhi-classroom',
  busy: false,
  closable: true,
  fragmentCount: 0,
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'confirm', value: { mode: SlideDeckMode; theme: V3Theme }): void
}>()

const modelMode = ref<SlideDeckMode>(props.mode)
const modelTheme = ref<V3Theme>(props.theme)

watch(() => props.open, open => {
  if (!open) return
  modelMode.value = props.mode
  modelTheme.value = props.theme
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

const pageEstimate = computed(() => {
  const base = Math.max(6, Math.ceil(props.fragmentCount / 3) + 3)
  if (modelMode.value === 'full') return `预计 ${base}–${base + 5} 页`
  if (modelMode.value === 'teaching') return `预计 ${Math.max(6, base - 2)}–${base + 2} 页`
  return `预计 ${Math.max(5, Math.round(base * .55))}–${Math.max(7, Math.round(base * .72))} 页`
})

function confirm() {
  emit('confirm', { mode: modelMode.value, theme: modelTheme.value })
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
.deck-generator__themes > button { padding:8px 8px 12px; text-align:left; border:1px solid #dce3eb; border-radius:15px; color:#263448; background:#fff; transition:.18s ease; }
.deck-generator__themes > button:hover,.deck-generator__themes > button.active { border-color:#6c91ec; box-shadow:0 9px 24px rgba(42,76,141,.1); transform:translateY(-1px); }
.deck-generator__themes > button.active { box-shadow:inset 0 0 0 1px #4d78df,0 9px 24px rgba(42,76,141,.11); }
.deck-generator__themes strong,.deck-generator__themes small { display:block; padding:0 4px; }
.deck-generator__themes strong { margin-top:9px; font-size:13px; }
.deck-generator__themes small { margin-top:3px; color:#7a8797; font-size:10px; }
.deck-theme-preview { --p:#fffdf7; --m:#2f6fe4; --a:#f29d38; position:relative; aspect-ratio:16/9; overflow:hidden; border-radius:9px; background:var(--p); box-shadow:inset 0 0 0 1px rgba(20,30,45,.08); }
.deck-theme-preview i { position:absolute; left:8%; top:15%; width:48%; height:9%; border-radius:6px; background:var(--m); }
.deck-theme-preview b { position:absolute; left:8%; top:31%; width:30%; height:4%; border-radius:5px; background:color-mix(in srgb,var(--m) 38%,transparent); }
.deck-theme-preview span { position:absolute; left:8%; bottom:14%; width:39%; height:34%; border-radius:7px; background:color-mix(in srgb,var(--m) 16%,var(--p)); }
.deck-theme-preview em { position:absolute; right:8%; bottom:14%; width:38%; height:50%; border-radius:10px 10px 3px 10px; background:var(--a); transform:skewY(-7deg); }
button[data-theme="academic-editorial"] .deck-theme-preview { --p:#fbfaf7; --m:#315e7d; --a:#b9aa90; }
button[data-theme="grid-notebook"] .deck-theme-preview { --p:#faf8f0; --m:#2d7464; --a:#d18a32; background-image:linear-gradient(#dce4de 1px,transparent 1px),linear-gradient(90deg,#dce4de 1px,transparent 1px); background-size:10px 10px; }
button[data-theme="modern-geometric"] .deck-theme-preview { --p:#f6f3ff; --m:#6548e8; --a:#f08b3e; }
button[data-theme="dark-tech"] .deck-theme-preview { --p:#0c1321; --m:#4db5ff; --a:#40d6b1; }
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
  .deck-generator__panel > footer { align-items:flex-start; flex-direction:column; }
}
</style>
