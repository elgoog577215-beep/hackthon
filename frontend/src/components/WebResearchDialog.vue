<template>
  <Teleport to="body">
    <div v-if="visible" class="research-overlay" @click.self="emit('close')">
      <section class="research-dialog" role="dialog" aria-modal="true" :aria-label="t('courseWorkbench.webResearch.title', '联网调研')">
        <header class="dialog-heading">
          <div>
            <span><Globe2 :size="18" /></span>
            <div><strong>{{ t('courseWorkbench.webResearch.title', '联网调研') }}</strong><small>{{ t('courseWorkbench.webResearch.subtitle', '说清要查什么，再审阅检索词和来源') }}</small></div>
          </div>
          <button type="button" :aria-label="t('common.close', '关闭')" @click="emit('close')"><X :size="19" /></button>
        </header>

        <div class="research-body">
          <aside class="research-brief">
            <label>
              <span>{{ t('courseWorkbench.webResearch.brief', '你想查什么？') }}</span>
              <textarea v-model="brief" rows="7" :placeholder="t('courseWorkbench.webResearch.briefPlaceholder', '例如：查找某位老师教材中对这个概念的公开讲解，同时补充大学和官方资料')" />
            </label>
            <label>
              <span>{{ t('courseWorkbench.webResearch.customQueries', '指定检索词（可选）') }}</span>
              <textarea v-model="customQueries" rows="3" :placeholder="t('courseWorkbench.webResearch.customQueriesPlaceholder', '每行一条；留空则根据调研要求自动生成')" />
            </label>
            <button class="search-action" type="button" :disabled="searching || brief.trim().length < 2" @click="runSearch">
              <LoaderCircle v-if="searching" :size="17" class="spin" /><Search v-else :size="17" />
              {{ searching ? t('courseWorkbench.webResearch.searching', '正在检索与筛选…') : t('courseWorkbench.webResearch.search', '开始检索') }}
            </button>

            <section v-if="session?.queries?.length" class="query-plan">
              <div><strong>{{ t('courseWorkbench.webResearch.queryPlan', '实际检索词') }}</strong><small>{{ session.queries.length }}</small></div>
              <span v-for="query in session.queries" :key="query">{{ query }}</span>
            </section>
            <p class="research-policy"><ShieldCheck :size="15" />{{ t('courseWorkbench.webResearch.policy', '网页只作参考来源；未标注开放许可时不逐字复用。') }}</p>
          </aside>

          <main class="research-results">
            <header>
              <div><strong>{{ t('courseWorkbench.webResearch.results', '来源候选') }}</strong><small v-if="session">{{ resultSummary }}</small></div>
              <span v-if="session?.provider">{{ session.provider }}</span>
            </header>

            <div v-if="loading" class="research-empty"><LoaderCircle :size="22" class="spin" />{{ t('courseWorkbench.webResearch.loadingHistory', '正在读取调研记录…') }}</div>
            <div v-else-if="!session" class="research-empty"><Search :size="24" /><strong>{{ t('courseWorkbench.webResearch.emptyTitle', '先描述这次要找的资料') }}</strong><span>{{ t('courseWorkbench.webResearch.emptyHelp', '系统会展示真实检索词，不会将结果直接写入课程。') }}</span></div>
            <div v-else-if="!session.results.length" class="research-empty"><CircleAlert :size="24" /><strong>{{ t('courseWorkbench.webResearch.noResults', '暂时没有可用来源') }}</strong><span>{{ failureMessage }}</span></div>
            <div v-else class="source-results">
              <label v-for="source in session.results" :key="source.source_id" class="source-result" :class="{ selected: selectedIds.has(source.source_id) }">
                <input :checked="selectedIds.has(source.source_id)" type="checkbox" @change="toggleSource(source.source_id)" />
                <div>
                  <div class="source-title"><strong>{{ source.title || source.domain }}</strong><span :class="`trust-${source.credibility}`">{{ trustLabel(source) }}</span></div>
                  <a :href="source.url" target="_blank" rel="noopener noreferrer" @click.stop>{{ source.domain || source.url }}<ExternalLink :size="12" /></a>
                  <p>{{ source.text }}</p>
                  <footer>
                    <span v-if="source.published_date"><CalendarDays :size="12" />{{ source.published_date }}</span>
                    <span v-if="source.license"><Scale :size="12" />{{ source.license }}</span>
                    <span v-if="source.sensitivity?.level === 'review_recommended'" class="review-warning"><TriangleAlert :size="12" />{{ t('courseWorkbench.webResearch.reviewRecommended', '敏感内容需复核') }}</span>
                  </footer>
                </div>
              </label>
            </div>
          </main>
        </div>

        <p v-if="error" class="research-error" role="alert">{{ error }}</p>
        <footer class="dialog-actions">
          <span>{{ t('courseWorkbench.webResearch.selectedCount', '已选 {count} 个来源').replace('{count}', String(selectedIds.size)) }}</span>
          <div><button type="button" @click="emit('close')">{{ t('common.cancel', '取消') }}</button><button class="save-action" type="button" :disabled="saving || !session" @click="saveSources"><LoaderCircle v-if="saving" :size="15" class="spin" />{{ saving ? t('courseWorkbench.webResearch.saving', '正在加入课程…') : t('courseWorkbench.webResearch.save', '加入当前阶段') }}</button></div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { CalendarDays, CircleAlert, ExternalLink, Globe2, LoaderCircle, Scale, Search, ShieldCheck, TriangleAlert, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import http, { teacherRequestConfig } from '../utils/http'

type WebResearchSource = {
  source_id: string
  url: string
  domain: string
  title: string
  text: string
  credibility: 'high' | 'medium' | 'low'
  trust_tier: string
  published_date?: string
  license?: string
  accepted_for_generation?: boolean
  sensitivity?: { level?: string; topics?: string[] }
}
type WebResearchSession = {
  session_id: string
  brief: string
  queries: string[]
  status: string
  provider: string
  provider_available: boolean
  results: WebResearchSource[]
  selected_source_ids: string[]
  rejected_count: number
  errors?: Array<{ code?: string }>
}

const props = defineProps<{ visible: boolean; courseId: string; stage: string; lessonId?: string }>()
const emit = defineEmits<{ (event: 'close'): void; (event: 'saved', references: any[]): void }>()
const brief = ref('')
const customQueries = ref('')
const session = ref<WebResearchSession | null>(null)
const selectedIds = ref(new Set<string>())
const loading = ref(false)
const searching = ref(false)
const saving = ref(false)
const error = ref('')
const resultSummary = computed(() => t('courseWorkbench.webResearch.resultSummary', '{count} 个可复核来源 · {rejected} 个低相关结果已过滤').replace('{count}', String(session.value?.results.length || 0)).replace('{rejected}', String(session.value?.rejected_count || 0)))
const failureMessage = computed(() => {
  const code = session.value?.errors?.[0]?.code || ''
  if (code === 'not_configured') return t('courseWorkbench.webResearch.notConfigured', '联网检索服务尚未配置')
  if (code === 'timeout') return t('courseWorkbench.webResearch.timeout', '本次检索超时，可缩小范围后重试')
  return t('courseWorkbench.webResearch.tryAgain', '可调整要求或指定更精确的检索词后重试。')
})

function errorText(reason: any, fallback: string) {
  const detail = reason?.response?.data?.detail
  return typeof detail === 'string' ? detail : String(detail?.message || reason?.message || fallback)
}
function setSession(value: WebResearchSession | null, autoSelect = false) {
  session.value = value
  if (!value) { selectedIds.value = new Set(); return }
  brief.value = value.brief || brief.value
  const selected = value.selected_source_ids?.length
    ? value.selected_source_ids
    : autoSelect
      ? value.results.filter(item => item.credibility === 'high' && item.sensitivity?.level !== 'review_recommended').map(item => item.source_id)
      : []
  selectedIds.value = new Set(selected)
}
async function loadLatest() {
  if (!props.visible || !props.courseId) return
  loading.value = true; error.value = ''
  try {
    const response = await http.get(`/api/courses/${props.courseId}/web-research`, teacherRequestConfig({ params: { stage: props.stage, lesson_id: props.lessonId || '' }, silentError: true }))
    setSession(response.data?.latest_session || null)
  } catch (reason: any) { error.value = errorText(reason, t('courseWorkbench.webResearch.loadFailed', '调研记录读取失败')) }
  finally { loading.value = false }
}
async function runSearch() {
  if (brief.value.trim().length < 2) return
  searching.value = true; error.value = ''
  try {
    const queries = customQueries.value.split(/\n+/).map(item => item.trim()).filter(Boolean).slice(0, 4)
    const response = await http.post(`/api/courses/${props.courseId}/web-research/search`, { brief: brief.value.trim(), stage: props.stage, lesson_id: props.lessonId || '', queries }, teacherRequestConfig({ silentError: true }))
    setSession(response.data, true)
  } catch (reason: any) { error.value = errorText(reason, t('courseWorkbench.webResearch.searchFailed', '联网检索失败')) }
  finally { searching.value = false }
}
function toggleSource(sourceId: string) {
  const next = new Set(selectedIds.value)
  if (next.has(sourceId)) next.delete(sourceId); else next.add(sourceId)
  selectedIds.value = next
}
function trustLabel(source: WebResearchSource) {
  if (source.credibility === 'high') return t('courseWorkbench.webResearch.highTrust', '高可信')
  if (source.credibility === 'medium') return t('courseWorkbench.webResearch.reviewTrust', '需确认')
  return t('courseWorkbench.webResearch.lowTrust', '低可信')
}
async function saveSources() {
  if (!session.value) return
  saving.value = true; error.value = ''
  try {
    const response = await http.put(`/api/courses/${props.courseId}/web-research/${session.value.session_id}`, { selected_source_ids: Array.from(selectedIds.value) }, teacherRequestConfig({ silentError: true }))
    emit('saved', response.data?.accepted_references || [])
    emit('close')
  } catch (reason: any) { error.value = errorText(reason, t('courseWorkbench.webResearch.saveFailed', '联网来源加入课程失败')) }
  finally { saving.value = false }
}

watch(() => [props.visible, props.courseId, props.stage, props.lessonId] as const, ([visible]) => { if (visible) void loadLatest() }, { immediate: true })
</script>

<style scoped>
.research-overlay{position:fixed;inset:0;z-index:2200;display:grid;place-items:center;padding:24px;background:rgba(15,23,42,.52);backdrop-filter:blur(2px)}.research-dialog{width:min(1180px,calc(100vw - 48px));height:min(780px,calc(100vh - 48px));display:grid;grid-template-rows:auto minmax(0,1fr) auto auto;overflow:hidden;border:1px solid #dce2ec;border-radius:16px;background:#fff;box-shadow:0 30px 80px rgba(15,23,42,.28)}.dialog-heading{min-height:68px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 20px;border-bottom:1px solid #e6eaf1}.dialog-heading>div{display:flex;align-items:center;gap:11px}.dialog-heading>div>span{width:36px;height:36px;display:grid;place-items:center;border-radius:9px;color:#4338ca;background:#eef2ff}.dialog-heading>div>div{display:grid;gap:3px}.dialog-heading strong{color:#1f2937;font-size:15px}.dialog-heading small{color:#64748b;font-size:12px}.dialog-heading>button{width:34px;height:34px;display:grid;place-items:center;border:0;border-radius:8px;color:#64748b;background:transparent;cursor:pointer}.research-body{min-height:0;display:grid;grid-template-columns:330px minmax(0,1fr)}.research-brief{min-height:0;overflow:auto;display:flex;flex-direction:column;gap:16px;padding:20px;border-right:1px solid #e6eaf1;background:#f8fafc}.research-brief label{display:grid;gap:7px}.research-brief label>span{color:#334155;font-size:12px;font-weight:750}.research-brief textarea{width:100%;padding:10px 11px;border:1px solid #cbd5e1;border-radius:9px;outline:0;resize:vertical;color:#1e293b;background:#fff;font:inherit;font-size:12px;line-height:1.6}.research-brief textarea:focus{border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.1)}.search-action{min-height:42px;display:flex;align-items:center;justify-content:center;gap:8px;border:1px solid #4f46e5;border-radius:9px;color:#fff;background:#4f46e5;font-size:13px;font-weight:750;cursor:pointer}.search-action:disabled{opacity:.5;cursor:not-allowed}.query-plan{display:grid;gap:7px;padding-top:4px}.query-plan>div{display:flex;align-items:center;justify-content:space-between;color:#334155;font-size:12px}.query-plan>div small{color:#64748b}.query-plan>span{padding:7px 8px;border:1px solid #dbe2ec;border-radius:7px;color:#475569;background:#fff;font-size:12px;line-height:1.45}.research-policy{display:flex;align-items:flex-start;gap:7px;margin:auto 0 0;color:#64748b;font-size:12px;line-height:1.5}.research-policy svg{flex:0 0 auto;color:#16a34a}.research-results{min-width:0;min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr)}.research-results>header{min-height:53px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 18px;border-bottom:1px solid #edf0f5}.research-results>header>div{display:flex;align-items:baseline;gap:9px}.research-results>header strong{color:#273449;font-size:13px}.research-results>header small,.research-results>header>span{color:#64748b;font-size:12px}.source-results{min-height:0;overflow:auto;display:grid;align-content:start;gap:9px;padding:14px 18px 28px}.source-result{display:grid;grid-template-columns:18px minmax(0,1fr);gap:10px;padding:13px;border:1px solid #e0e6ef;border-radius:10px;background:#fff;cursor:pointer}.source-result.selected{border-color:#a5b4fc;background:#f8f8ff}.source-result>input{margin-top:3px;accent-color:#4f46e5}.source-result>div{min-width:0}.source-title{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.source-title strong{overflow:hidden;color:#273449;font-size:13px;line-height:1.45;text-overflow:ellipsis;white-space:nowrap}.source-title span{flex:0 0 auto;padding:2px 6px;border-radius:999px;font-size:12px;font-weight:750}.trust-high{color:#15803d;background:#dcfce7}.trust-medium{color:#a16207;background:#fef9c3}.trust-low{color:#b91c1c;background:#fee2e2}.source-result a{display:inline-flex;align-items:center;gap:4px;max-width:100%;margin-top:3px;overflow:hidden;color:#4f46e5;font-size:12px;text-decoration:none;text-overflow:ellipsis;white-space:nowrap}.source-result p{display:-webkit-box;overflow:hidden;-webkit-box-orient:vertical;-webkit-line-clamp:3;margin:8px 0 0;color:#64748b;font-size:12px;line-height:1.55}.source-result footer{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px;color:#64748b;font-size:12px}.source-result footer span{display:flex;align-items:center;gap:4px}.source-result footer .review-warning{color:#b45309}.research-empty{min-height:260px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:9px;padding:32px;color:#64748b;text-align:center;font-size:12px}.research-empty strong{color:#334155;font-size:14px}.research-empty span{max-width:420px;line-height:1.6}.research-error{margin:0;padding:9px 20px;color:#b91c1c;background:#fff1f2;font-size:12px}.dialog-actions{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 20px;border-top:1px solid #e6eaf1}.dialog-actions>span{color:#64748b;font-size:12px}.dialog-actions>div{display:flex;gap:9px}.dialog-actions button{min-height:36px;padding:0 13px;border:1px solid #cfd7e3;border-radius:8px;color:#475569;background:#fff;font-size:12px;font-weight:700;cursor:pointer}.dialog-actions .save-action{display:flex;align-items:center;gap:6px;border-color:#4f46e5;color:#fff;background:#4f46e5}.dialog-actions button:disabled{opacity:.5;cursor:not-allowed}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:760px){.research-overlay{padding:0}.research-dialog{width:100vw;height:100vh;border:0;border-radius:0}.research-body{grid-template-columns:1fr;overflow:auto}.research-brief{overflow:visible;border-right:0;border-bottom:1px solid #e6eaf1}.research-results{min-height:420px}.source-results{overflow:visible}.dialog-actions{position:sticky;bottom:0;background:#fff}.dialog-actions>span{display:none}}
</style>
