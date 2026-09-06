<template>
  <div v-if="open" class="template-creator" role="dialog" aria-modal="true">
    <section class="template-creator__panel">
      <header>
        <div>
          <small>PPT TEMPLATE COMPILER</small>
          <h2>{{ t('pptTemplatePacks.creatorTitle', '创建个人 PPT 模板') }}</h2>
          <p>{{ t('pptTemplatePacks.compileHint', '系统会提取视觉语言并生成 8 页预览，不需要制作 .pptpack。') }}</p>
        </div>
        <button type="button" :aria-label="t('common.close', '关闭')" @click="emit('close')"><X :size="18" /></button>
      </header>

      <div v-if="!draft" class="template-creator__body">
        <div class="template-creator__modes">
          <button type="button" :class="{ active: mode === 'upload' }" @click="mode = 'upload'">
            <FileUp :size="18" />{{ t('pptTemplatePacks.uploadMode', '上传参考 PPTX') }}
          </button>
          <button type="button" :class="{ active: mode === 'brand' }" @click="mode = 'brand'">
            <Palette :size="18" />{{ t('pptTemplatePacks.brandMode', '品牌向导') }}
          </button>
        </div>

        <div class="template-creator__fields">
          <label>
            <span>{{ t('pptTemplatePacks.name', '模板名称') }}</span>
            <input v-model.trim="name" maxlength="80" placeholder="例如：学院蓝 2026" />
          </label>
          <label>
            <span>{{ t('pptTemplatePacks.baseTheme', '规划回退主题') }}</span>
            <select v-model="baseTheme">
              <option v-for="theme in themes" :key="theme.value" :value="theme.value">{{ theme.label }}</option>
            </select>
          </label>
          <label v-if="mode === 'upload'" class="template-creator__file">
            <span>{{ t('pptTemplatePacks.referencePptx', '参考 PPTX') }}</span>
            <input type="file" accept=".pptx,.potx,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.openxmlformats-officedocument.presentationml.template" @change="pickReference" />
            <small>{{ referencePptx?.name || t('pptTemplatePacks.referencePptxHint', '建议包含封面、章节、内容、练习、图表或代码、结束页') }}</small>
          </label>
          <label class="template-creator__file">
            <span>{{ t('pptTemplatePacks.logo', 'Logo（可选）') }}</span>
            <input type="file" accept=".png,.svg,.jpg,.jpeg,.webp,image/*" @change="pickLogo" />
            <small>{{ logo?.name || t('pptTemplatePacks.logoHint', 'PNG / SVG / JPEG / WebP') }}</small>
          </label>
          <label class="template-creator__file">
            <span>{{ t('pptTemplatePacks.referenceImages', '风格参考图（可选）') }}</span>
            <input type="file" multiple accept=".png,.svg,.jpg,.jpeg,.webp,image/*" @change="pickReferences" />
            <small>{{ referenceImages.length ? t('pptTemplatePacks.selectedImages', '已选择 {count} 张').replace('{count}', String(referenceImages.length)) : t('pptTemplatePacks.referenceImagesHint', '可上传 2–5 张背景或装饰参考图') }}</small>
          </label>
          <label>
            <span>{{ t('pptTemplatePacks.primaryColor', '主色') }}</span>
            <div class="template-creator__color"><input v-model="primaryColor" type="color" /><input v-model.trim="primaryColor" maxlength="7" /></div>
          </label>
          <label>
            <span>{{ t('pptTemplatePacks.fontName', '字体名称') }}</span>
            <input v-model.trim="fontName" placeholder="例如：Noto Sans SC" />
          </label>
        </div>
        <p v-if="store.error" class="template-creator__error">{{ store.error }}</p>
      </div>

      <div v-else class="template-creator__preview">
        <div class="template-creator__ready">
          <CheckCircle2 :size="22" />
          <div><strong>{{ t('pptTemplatePacks.ready', '预览已就绪') }}</strong><small>{{ draft.name }} · {{ draft.extracted_style?.aspect_ratio || '16:9' }}</small></div>
        </div>
        <p class="template-creator__extraction-summary">
          {{ extractionSummary }}
        </p>
        <p v-if="draft.extracted_style?.requires_widescreen_confirmation" class="template-creator__notice">
          {{ t('pptTemplatePacks.widescreenNotice', '原模板为 4:3，发布后会适配为 16:9。请确认代表页预览的安全区。') }}
        </p>
        <div v-if="draft.representative_pages?.length" class="template-creator__representatives">
          <label v-for="page in draft.representative_pages" :key="String(page.role)">
            <span>{{ t('pptTemplatePacks.representativePage', '{role}代表页').replace('{role}', previewLabel(String(page.role))) }}</span>
            <select v-model.number="page.slide_number">
              <option
                v-for="pageNumber in Math.max(1, Number(draft.extracted_style?.slide_count || 1))"
                :key="pageNumber"
                :value="pageNumber"
              >{{ t('pptTemplatePacks.pageNumber', '第 {count} 页').replace('{count}', String(pageNumber)) }}</option>
            </select>
          </label>
        </div>
        <div class="template-creator__preview-grid">
          <article
            v-for="(slide, index) in draft.preview_slides || []"
            :key="String(slide.role)"
            :data-role="String(slide.role)"
            :style="previewStyle(String(slide.role))"
          >
            <span>{{ String(index + 1).padStart(2, '0') }}</span>
            <div>
              <strong>{{ previewLabel(String(slide.role)) }}</strong>
              <small>{{ t('pptTemplatePacks.editablePreview', '可编辑文本 · {theme}').replace('{theme}', baseThemeLabel) }}</small>
            </div>
          </article>
        </div>
      </div>

      <footer>
        <button type="button" class="secondary" :disabled="store.saving" @click="draft ? reset() : emit('close')">
          {{ draft ? t('pptTemplatePacks.restart', '重新填写') : t('common.cancel', '取消') }}
        </button>
        <button v-if="!draft" type="button" :disabled="!canCreate || store.saving" @click="createDraft">
          <LoaderCircle v-if="store.saving" class="spinning" :size="17" />
          <Sparkles v-else :size="17" />
          {{ store.saving ? t('pptTemplatePacks.creating', '正在分析模板…') : t('pptTemplatePacks.createDraft', '生成模板预览') }}
        </button>
        <button v-else type="button" :disabled="store.saving" @click="publish">
          <LoaderCircle v-if="store.saving" class="spinning" :size="17" />
          <Library v-else :size="17" />
          {{ store.saving ? t('pptTemplatePacks.publishing', '正在发布…') : t('pptTemplatePacks.publish', '发布到我的模板') }}
        </button>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { CheckCircle2, FileUp, Library, LoaderCircle, Palette, Sparkles, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import { resolvePublicAssetUrl } from '../utils/publicAssetUrl'
import {
  usePptTemplatePacksStore,
  type BuiltinPptTheme,
  type PersonalPptTemplatePack,
} from '../stores/pptTemplatePacks'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (event: 'close'): void
  (event: 'published', value: PersonalPptTemplatePack): void
}>()

const store = usePptTemplatePacksStore()
const mode = ref<'upload' | 'brand'>('upload')
const name = ref('')
const baseTheme = ref<BuiltinPptTheme>('qizhi-classroom')
const referencePptx = ref<File | null>(null)
const logo = ref<File | null>(null)
const referenceImages = ref<File[]>([])
const primaryColor = ref('#2F6FE4')
const fontName = ref('Noto Sans SC')
const draft = ref<PersonalPptTemplatePack | null>(null)

const themes: Array<{ value: BuiltinPptTheme; label: string }> = [
  { value: 'qizhi-classroom', label: t('pptTemplatePacks.themes.qizhi', '启智课堂') },
  { value: 'academic-editorial', label: t('pptTemplatePacks.themes.academic', '学术编辑') },
  { value: 'grid-notebook', label: t('pptTemplatePacks.themes.grid', '网格笔记') },
  { value: 'modern-geometric', label: t('pptTemplatePacks.themes.modern', '现代几何') },
  { value: 'dark-tech', label: t('pptTemplatePacks.themes.dark', '深色科技') },
]

const canCreate = computed(() => (
  name.value.length > 0
  && (mode.value === 'brand' || Boolean(referencePptx.value))
))
const baseThemeLabel = computed(() => themes.find(item => item.value === baseTheme.value)?.label || baseTheme.value)
const extractionSummary = computed(() => {
  const extracted = draft.value?.extracted_style || {}
  return t(
    'pptTemplatePacks.extractionSummary',
    '已分析 {slides} 页、{boxes} 个文本框、{images} 个图片素材。',
  )
    .replace('{slides}', String(extracted.slide_count || 0))
    .replace('{boxes}', String(extracted.text_box_structure?.total || 0))
    .replace('{images}', String(extracted.media_inventory?.length || 0))
})

watch(() => props.open, open => {
  if (open) return
  reset()
})

function selectedFile(event: Event) {
  return (event.target as HTMLInputElement).files?.[0] || null
}
function pickReference(event: Event) {
  referencePptx.value = selectedFile(event)
}
function pickLogo(event: Event) {
  logo.value = selectedFile(event)
}
function pickReferences(event: Event) {
  referenceImages.value = Array.from(
    (event.target as HTMLInputElement).files || [],
  ).slice(0, 5)
}
async function createDraft() {
  if (!canCreate.value) return
  draft.value = await store.createDraft({
    name: name.value,
    baseTheme: baseTheme.value,
    referencePptx: mode.value === 'upload' ? referencePptx.value : null,
    logo: logo.value,
    referenceImages: referenceImages.value,
    brand: { primary_color: primaryColor.value, font_name: fontName.value },
  })
}
async function publish() {
  if (!draft.value) return
  if (draft.value.representative_pages?.length) {
    draft.value = await store.updateDraft(draft.value.pack_id, {
      representative_pages: draft.value.representative_pages.map(page => ({
        ...page,
        confirmed: true,
      })),
    })
  }
  const published = await store.publish(draft.value.pack_id)
  emit('published', published)
  emit('close')
}
function reset() {
  mode.value = 'upload'
  name.value = ''
  baseTheme.value = 'qizhi-classroom'
  referencePptx.value = null
  logo.value = null
  referenceImages.value = []
  primaryColor.value = '#2F6FE4'
  fontName.value = 'Noto Sans SC'
  draft.value = null
}
function previewLabel(role: string) {
  const labels = {
    cover: t('pptTemplatePacks.roles.cover', '封面'),
    chapter: t('pptTemplatePacks.roles.chapter', '章节'),
    objectives: t('pptTemplatePacks.roles.objectives', '目标'),
    definition: t('pptTemplatePacks.roles.definition', '定义'),
    process: t('pptTemplatePacks.roles.process', '推演'),
    practice: t('pptTemplatePacks.roles.practice', '练习'),
    evidence: t('pptTemplatePacks.roles.evidence', '证据'),
    recap: t('pptTemplatePacks.roles.recap', '复盘'),
  } as Record<string, string>
  return labels[role] || role
}
function previewStyle(role: string): Record<string, string> {
  const token = draft.value?.compiled_theme || {}
  const assetName = ({
    cover: 'cover',
    chapter: 'chapter',
    process: 'interior_reasoning',
    practice: 'interior_practice',
    evidence: 'interior_evidence',
    recap: 'recap',
  } as Record<string, string>)[role] || 'interior_content'
  const webPath = token.visual_assets?.[assetName]?.web_path
  return {
    '--preview-title': `#${token.title || '243B53'}`,
    '--preview-accent': `#${token.accent || '3265D9'}`,
    '--preview-surface': `#${token.surface || 'FFFFFF'}`,
    '--preview-soft': `#${token.accent_soft || 'EEF3FF'}`,
    backgroundImage: webPath
      ? `url("${resolvePublicAssetUrl(webPath, import.meta.env.BASE_URL)}")`
      : 'none',
  }
}
</script>

<style scoped>
.template-creator { position:fixed; inset:52px 0 0; z-index:140; display:grid; place-items:center; padding:28px; color:#182433; background:rgba(17,25,38,.76); backdrop-filter:blur(18px); }
.template-creator__panel { width:min(860px,100%); max-height:calc(100vh - 100px); overflow:auto; border:1px solid rgba(255,255,255,.75); border-radius:24px; background:#f8fafc; box-shadow:0 30px 90px rgba(4,12,26,.34); }
.template-creator__panel > header { display:flex; justify-content:space-between; gap:24px; padding:28px 32px 22px; border-bottom:1px solid #e3e9f0; background:linear-gradient(135deg,#fff,#f2f6fc); }
.template-creator__panel > header small { color:#3265d9; font-size:11px; font-weight:850; letter-spacing:.16em; }
.template-creator__panel > header h2 { margin:7px 0 5px; font-size:26px; }
.template-creator__panel > header p { margin:0; color:#68778a; font-size:13px; }
.template-creator__panel > header button { width:34px; height:34px; display:grid; place-items:center; border:1px solid #dce3eb; border-radius:10px; color:#536276; background:#fff; }
.template-creator__body,.template-creator__preview { padding:24px 32px; }
.template-creator__modes { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:20px; }
.template-creator__modes button { min-height:48px; display:flex; align-items:center; justify-content:center; gap:8px; border:1px solid #dce3eb; border-radius:12px; color:#607086; background:#fff; font-weight:750; }
.template-creator__modes button.active { border-color:#5e84e5; color:#2858c3; background:#eef3ff; box-shadow:inset 0 0 0 1px #5e84e5; }
.template-creator__fields { display:grid; grid-template-columns:1fr 1fr; gap:15px; }
.template-creator__fields label { display:grid; gap:7px; color:#536276; font-size:12px; font-weight:750; }
.template-creator__fields input,.template-creator__fields select { min-height:42px; padding:0 12px; border:1px solid #d8e0e9; border-radius:10px; color:#263448; background:#fff; }
.template-creator__file input { padding:8px; }
.template-creator__file small { color:#8290a2; font-weight:500; }
.template-creator__color { display:grid; grid-template-columns:48px 1fr; gap:8px; }
.template-creator__color input[type="color"] { width:48px; padding:4px; }
.template-creator__error,.template-creator__notice { padding:10px 12px; border-radius:9px; color:#9f3f32; background:#fff0ed; font-size:12px; }
.template-creator__ready { display:flex; align-items:center; gap:10px; color:#16856b; }
.template-creator__ready > div { display:grid; gap:3px; }
.template-creator__ready small { color:#728195; }
.template-creator__extraction-summary { margin:12px 0 0; color:#65758a; font-size:12px; }
.template-creator__preview-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-top:18px; }
.template-creator__representatives { display:grid; grid-template-columns:repeat(3,1fr); gap:9px; margin-top:16px; }
.template-creator__representatives label { display:grid; grid-template-columns:1fr 100px; align-items:center; gap:8px; padding:8px 10px; border:1px solid #dce3eb; border-radius:9px; color:#59697e; background:#fff; font-size:11px; font-weight:700; }
.template-creator__representatives select { min-height:32px; border:1px solid #d8e0e9; border-radius:7px; color:#263448; background:#fff; }
.template-creator__preview-grid article { position:relative; aspect-ratio:16/9; display:grid; align-content:end; gap:3px; padding:12px; overflow:hidden; border:1px solid #dce3eb; border-radius:12px; color:var(--preview-title); background-color:var(--preview-surface); background-position:center; background-size:cover; box-shadow:0 7px 16px rgba(31,48,73,.12); }
.template-creator__preview-grid article > div { position:relative; display:grid; gap:2px; padding:8px 9px 8px 12px; border-radius:7px; background:color-mix(in srgb,var(--preview-surface) 91%,transparent); box-shadow:3px 4px 0 color-mix(in srgb,var(--preview-accent) 22%,transparent); }
.template-creator__preview-grid article > div::before { position:absolute; inset:7px auto 7px 0; width:3px; border-radius:3px; background:var(--preview-accent); content:''; }
.template-creator__preview-grid span { position:absolute; top:9px; right:10px; color:var(--preview-accent); font-size:9px; font-weight:850; }
.template-creator__preview-grid strong { font-size:12px; }
.template-creator__preview-grid small { color:color-mix(in srgb,var(--preview-title) 64%,transparent); font-size:8px; }
.template-creator__panel > footer { display:flex; justify-content:flex-end; gap:10px; padding:20px 32px 25px; border-top:1px solid #e3e9f0; }
.template-creator__panel > footer button { min-height:42px; display:flex; align-items:center; gap:8px; padding:0 20px; border:0; border-radius:11px; color:#fff; background:#2f63da; font-weight:750; }
.template-creator__panel > footer button.secondary { color:#5f6f83; border:1px solid #d9e1ea; background:#fff; }
.template-creator__panel > footer button:disabled { opacity:.55; }
.spinning { animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
@media (max-width:700px) { .template-creator__fields,.template-creator__preview-grid { grid-template-columns:1fr; } }
</style>
