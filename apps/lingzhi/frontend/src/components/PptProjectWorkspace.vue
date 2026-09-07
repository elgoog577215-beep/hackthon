<!--
THESIS: Build one presentation from an explicit selection, then review, then render.
OWN-WORLD: Existing teacher workbench, shared document controls and context sidebar.
STORY: The teacher sees the selected sources, approves editable pages and receives the deck.
FIRST VIEWPORT: Compact step toolbar; lecture and file lists; selection summary and Next at the foot.
FORM: User-pinned three-step workspace. Existing manuscript editor and renderer remain authoritative.
-->
<template>
  <section class="ppt-project-workspace">
    <header class="project-toolbar">
      <div class="project-title"><h2>PPT</h2></div>
      <nav v-if="!embedded" :aria-label="t('pptProject.steps')">
        <UiSegmentedControl :model-value="String(step)" :options="stepOptions" :accessibility-label="t('pptProject.steps')" @update:model-value="selectStep(Number($event))" />
      </nav>
      <button v-if="embedded" class="project-legacy" type="button" :disabled="dirty" @click="emit('legacy')">{{ t('pptProject.originalReview') }}</button>
      <button v-else type="button" @click="back">{{ t('pptProject.back') }}</button>
    </header>
    <div v-if="error" class="project-message is-error" role="alert">{{ error }}</div>
    <div v-if="project?.source_state === 'stale'" class="project-message" role="status">{{ t('pptProject.stale') }}</div>
    <section v-if="step === 1" class="project-selection">
      <div class="selection-columns">
        <section><h2>{{ t('pptProject.lectures') }}</h2>
          <p v-if="!catalog?.lectures?.length" class="empty-copy">{{ t('pptProject.noLectures') }}</p>
          <label v-for="lecture in catalog?.lectures || []" :key="lecture.lesson_id" class="source-row" :class="{ unavailable: !lecture.ready }">
            <input v-model="lessonIds" type="checkbox" :value="lecture.lesson_id" :disabled="!lecture.ready || busy" />
            <span>{{ lecture.title }}</span><small v-if="!lecture.ready">{{ t('pptProject.noHandout') }}</small>
          </label>
        </section>
        <section><div class="source-heading"><h2>{{ t('pptProject.materials') }}</h2><button type="button" :disabled="busy" @click="fileInput?.click()"><Plus :size="15" />{{ t('pptProject.upload') }}</button></div>
          <input ref="fileInput" class="file-input" type="file" multiple accept=".pdf,.doc,.docx,.ppt,.pptx,.md,.txt,.xlsx,.csv,.html" @change="upload" />
          <button v-if="!catalog?.uploads?.length" type="button" class="upload-area" :disabled="busy" @click="fileInput?.click()"><Upload :size="22" /><strong>{{ t('pptProject.uploadTitle') }}</strong><span>PDF · Word · PowerPoint · Markdown</span></button>
          <label v-for="file in catalog?.uploads || []" :key="file.asset_id" class="source-row"><input v-model="assetIds" type="checkbox" :value="file.asset_id" :disabled="busy" /><FileText :size="16" /><span>{{ file.filename }}</span></label>
        </section>
      </div>
      <section v-if="catalog?.projects?.length" class="existing-projects"><h2>{{ t('pptProject.recent') }}</h2><button v-for="item in catalog.projects" :key="item.project_id" type="button" :disabled="busy" @click="openProject(item.project_id)"><Presentation :size="15" /><span>{{ item.title }}</span><ChevronRight :size="16" /></button></section>
      <footer class="selection-footer"><span>{{ selectionSummary }}</span><button v-if="!embedded" type="button" class="primary" :disabled="busy || !selectionReady" @click="prepare">{{ busy ? t('pptProject.working') : (project && !selectionMatches ? t('pptProject.newFromSelection') : t('pptProject.next')) }}<ArrowRight :size="16" /></button></footer>
    </section>
    <template v-else>
      <div v-if="running" class="project-progress" role="status"><LoaderCircle :size="18" class="spinning" /><span>{{ project?.status === 'rendering' ? t('pptProject.rendering') : t('pptProject.preparing') }}</span><progress :value="project?.job?.progress || 0" max="100" /><button type="button" @click="pause">{{ t('pptProject.pause') }}</button></div>
      <div v-if="project?.status === 'paused'" class="project-message"><span>{{ t('pptProject.paused') }}</span><button type="button" :disabled="busy || project.source_state === 'stale'" @click="resume">{{ t('pptProject.retry') }}</button></div>
      <template v-if="step === 2">
        <PptManuscriptWorkflow v-if="project?.manuscript" ref="editor" embedded :external-actions="embedded" :allow-page-regeneration="false" :title="project.title" :state="manuscriptState" :busy="busy || running || project.source_state === 'stale'"
          :saving="saving" :confirming="confirming" @save-manuscript="save" @confirm-manuscript="confirm"
          @generate-ppt="selectStep(3)" @dirty-change="dirty = $event" @generate-manuscript="rebuild" @regenerate-manuscript="rebuild" />
        <div v-else-if="!running" class="project-empty">{{ t('pptProject.noDraft') }}<button v-if="project?.status === 'selected'" type="button" class="primary" :disabled="busy || project.source_state === 'stale'" @click="rebuild">{{ t('pptProject.retry') }}</button></div>
      </template>
      <section v-else class="project-render">
        <header><div><h1>{{ project?.title }}</h1><p>{{ renderedCurrent ? t('pptProject.ready') : t('pptProject.renderHint') }}</p></div>
          <button v-if="!embedded && project?.last_good_render" type="button" :disabled="busy" @click="download"><Download :size="16" />{{ t('pptProject.export') }}</button>
          <button v-if="!embedded && !renderedCurrent" type="button" class="primary" :disabled="busy || running || !canRender" @click="render"><Presentation :size="16" />{{ t('pptProject.render') }}</button>
        </header>
        <p v-if="project?.last_good_render && !renderedCurrent" class="empty-copy">{{ t('pptProject.previous') }}</p>
        <div v-if="slides.length" class="project-deck"><nav :aria-label="t('pptProject.pages')"><button v-for="(slide, index) in slides" :key="index" type="button" :class="{active:page === index}" @click="page = index"><span>{{ index + 1 }}</span>{{ slide.title }}</button></nav><div class="project-canvas"><SlideCanvas :slide="slides[page] as any" :page-number="page + 1" :page-count="slides.length" :deck-title="project.title" :theme="project.theme" :course-id="courseId" /></div></div>
      </section>
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, ChevronRight, Download, FileText, LoaderCircle, Plus, Presentation, Upload } from 'lucide-vue-next'
import http, { identityRequestConfig } from '../utils/http'
import { t } from '../shared/i18n'
import PptManuscriptWorkflow from './PptManuscriptWorkflow.vue'
import SlideCanvas from './SlideCanvas.vue'
import UiSegmentedControl from './UiSegmentedControl.vue'
import { adaptSlideDeckV6ForWeb } from '../utils/slide-deck-v6-adapter'
const props = defineProps<{courseId:string; initialLessonId?:string; sourceRevision?:string; embedded?:boolean}>()
const emit = defineEmits<{(event:'legacy'):void}>()
const router = useRouter(), fileInput = ref<HTMLInputElement>(), editor = ref<InstanceType<typeof PptManuscriptWorkflow>>()
const catalog = ref<any>(), project = ref<any>(), lessonIds = ref<string[]>([]), assetIds = ref<string[]>([])
const step = ref(1), page = ref(0), error = ref(''), busy = ref(false), saving = ref(false), confirming = ref(false), dirty = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
let controller = new AbortController()
let contextVersion = 0, pollVersion = 0, catalogVersion = 0
const base = () => `/api/teacher/courses/${encodeURIComponent(props.courseId)}/ppt-projects`
const url = (action='') => `${base()}/${project.value.project_id}${action ? '/' + action : ''}`
const config = () => identityRequestConfig('teacher', {signal:controller.signal})
const selectionMatches = computed(() => project.value && JSON.stringify(lessonIds.value) === JSON.stringify(project.value.lesson_ids || []) && JSON.stringify(assetIds.value) === JSON.stringify(project.value.asset_ids || []))
const selectionReady = computed(() => !!catalog.value && (lessonIds.value.length > 0 || assetIds.value.length > 0)
 && lessonIds.value.every(id => catalog.value.lectures?.some((item:any) => item.lesson_id === id && item.ready))
 && assetIds.value.every(id => catalog.value.uploads?.some((item:any) => item.asset_id === id)))
const stepLabels = computed(() => [t('pptProject.select'),t('pptProject.review'),t('pptProject.finish')])
const stepOptions = computed(() => stepLabels.value.map((label, index) => ({ label, value: String(index + 1), disabled: !canStep(index + 1) })))
const running = computed(() => ['building','rendering'].includes(project.value?.status))
const canRender = computed(() => project.value?.confirmed_revision && project.value?.confirmed_revision === project.value?.manuscript?.manuscript_revision && project.value?.source_state !== 'stale' && !dirty.value)
const renderedCurrent = computed(() => project.value?.last_good_render?.manuscript_revision === project.value?.manuscript?.manuscript_revision && project.value?.last_good_render && project.value?.source_state !== 'stale')
const slides = computed(() => project.value?.last_good_render ? adaptSlideDeckV6ForWeb(project.value.last_good_render.deck) : [])
const manuscriptState = computed(() => ({...project.value, generation_branch:'manuscript_first', status:canRender.value?'confirmed':'draft', can_generate_ppt:canRender.value, layouts:project.value?.layouts || []}))
const selectionSummary = computed(() => t('pptProject.selected').replace('{lessons}', String(lessonIds.value.length)).replace('{files}', String(assetIds.value.length)))
const sources = computed(() => ({
 lectures: (catalog.value?.lectures || []).filter((item:any) => lessonIds.value.includes(item.lesson_id)),
 files: (catalog.value?.uploads || []).filter((item:any) => assetIds.value.includes(item.asset_id)),
}))
const context = computed(() => {
 const phase: 'before'|'during'|'after'|'failed' = error.value || project.value?.error ? 'failed' : running.value || project.value?.status === 'paused' ? 'during' : project.value?.manuscript ? 'after' : 'before'
 const blocked = busy.value || running.value || dirty.value
 const stale = project.value?.source_state === 'stale'
 const actions: {id:string;label:string;primary?:boolean;disabled?:boolean;reason?:string}[] = []
 if (running.value) actions.push({id:'pause',label:t('pptProject.pause'),disabled:busy.value})
 else if (project.value?.status === 'paused') actions.push({id:'resume',label:t('pptProject.retry'),primary:true,disabled:blocked || stale})
 if (step.value === 1) actions.push({id:'prepare',label:project.value && !selectionMatches.value ? t('pptProject.newFromSelection') : t('pptWorkspace.generateManuscript'),primary:true,disabled:blocked || !selectionReady.value})
 else {
  actions.push({id:'sources',label:t('pptProject.select'),disabled:blocked})
  if (project.value?.manuscript) actions.push({id:'review',label:t('pptProject.review'),disabled:blocked})
  if (project.value?.manuscript && !canRender.value && !stale) actions.push({id:'confirm',label:t('pptWorkspace.confirmManuscript'),primary:true,disabled:blocked || !project.value.confirmable})
  if (canRender.value && !renderedCurrent.value) actions.push({id:'render',label:t('pptProject.render'),primary:true,disabled:blocked})
  if (project.value?.last_good_render) actions.push({id:'preview',label:t('courseFiles.openPpt'),disabled:blocked},{id:'download',label:t('pptProject.export'),disabled:busy.value})
  if (!project.value?.manuscript && !running.value && project.value?.status !== 'paused') actions.push({id:'prepare',label:t('pptProject.retry'),primary:true,disabled:blocked || stale})
 }
 return { phase, preparing: false, label: running.value ? (project.value?.status === 'rendering' ? t('pptProject.rendering') : t('pptProject.preparing')) : project.value?.status === 'paused' ? t('pptProject.paused') : phase === 'failed' ? t('courseWorkbench.contextPane.failed') : project.value?.manuscript ? t('courseWorkbench.contextPane.ready') : t('courseWorkbench.contextPane.prepare'), detail:error.value || project.value?.error?.message || (stale ? t('pptProject.stale') : selectionSummary.value), progress:running.value ? project.value?.job?.progress || 0 : null, actions }
})
async function runContextAction(id:string) {
 if (!context.value.actions.some(item => item.id === id && !item.disabled)) return
 if (id === 'sources') return selectStep(1)
 if (id === 'review') return selectStep(2)
 if (id === 'preview') return selectStep(3)
 if (id === 'prepare') return prepare()
 if (id === 'confirm') return confirm()
 if (id === 'render') {selectStep(3);return render()}
 if (id === 'download') return download()
 if (id === 'pause') return pause()
 if (id === 'resume') return resume()
}
function failure(e:any) { if (e?.code === 'ERR_CANCELED') return; const detail=e?.response?.data?.detail; error.value = (typeof detail === 'object' ? detail?.message : typeof detail === 'string' ? detail : '') || (e?.response?.status === 409 ? t('pptProject.conflict') : t('pptProject.failed')) }
async function loadCatalog() { const version=contextVersion, request=++catalogVersion; try {const {data}=await http.get(base(),config());if(version===contextVersion && request===catalogVersion){catalog.value=data;if(step.value===1)lessonIds.value=lessonIds.value.filter(id=>data.lectures?.some((item:any)=>item.lesson_id===id && item.ready))}} catch(e){if(version===contextVersion && request===catalogVersion)failure(e)} }
function canStep(target:number) {return !dirty.value && !busy.value && (target === 1 || (target === 2 && project.value) || (target === 3 && (canRender.value || project.value?.last_good_render)))}
function selectStep(target:number) {if(canStep(target)) step.value=target}
async function poll() {if(timer)clearTimeout(timer);if(disposed || !project.value) return; const version=contextVersion, request=++pollVersion, id=project.value.project_id; try {const {data}=await http.get(url(),config());if(version!==contextVersion || request!==pollVersion || project.value?.project_id!==id)return;project.value=data} catch(e){if(version===contextVersion)failure(e)}; if(running.value && !disposed && version===contextVersion && request===pollVersion) timer=setTimeout(poll,1800)}
async function openProject(id:string) {if(busy.value || dirty.value)return;busy.value=true;project.value={project_id:id};page.value=0;try{await poll();lessonIds.value=[...(project.value?.lesson_ids || [])];assetIds.value=[...(project.value?.asset_ids || [])];step.value=project.value?.status==='ready'?3:2}finally{busy.value=false}}
async function upload(event:Event) {const files=Array.from((event.target as HTMLInputElement).files || []);busy.value=true;error.value='';try{for(const file of files){const form=new FormData();form.append('file',file);const {data}=await http.post(`${base()}/uploads`,form,config());assetIds.value.push(data.asset_id)}await loadCatalog()}catch(e){failure(e)}finally{busy.value=false;(event.target as HTMLInputElement).value=''}}
async function prepare(){
 if(busy.value || !selectionReady.value)return
 const reuse=selectionMatches.value && project.value?.source_state !== 'stale'
 if(reuse && (project.value?.manuscript || running.value)){step.value=2;return}
 busy.value=true;error.value=''
 try{
  if(!reuse){project.value=(await http.post(base(),{lesson_ids:lessonIds.value,asset_ids:assetIds.value,expected_revision:catalog.value.document_revision},config())).data}
  step.value=2
  await http.post(url('prepare'),{expected_revision:project.value.revision},config())
  await poll();await loadCatalog()
 }catch(e){failure(e)}finally{busy.value=false}
}
async function action(name:string){busy.value=true;error.value='';try{project.value=(await http.post(url(name),{expected_revision:project.value.revision},config())).data;await poll()}catch(e){failure(e)}finally{busy.value=false}}
async function save(updates:Record<string,any>[],pacing?:Record<string,any>){saving.value=true;busy.value=true;try{project.value=(await http.patch(url('manuscript'),{expected_revision:project.value.revision,page_updates:updates,pacing},config())).data;dirty.value=false;await poll()}catch(e){failure(e)}finally{saving.value=false;busy.value=false}}
async function confirm(){confirming.value=true;await action('confirm');confirming.value=false;if(canRender.value && !props.embedded)step.value=3}
async function render(){await action('render')}
async function rebuild(){if(!dirty.value)await action('prepare')}
async function pause(){await action('pause')}
async function resume(){await action(project.value?.job?.request_snapshot?.render?'render':'prepare')}
async function download(){busy.value=true;try{const {data}=await http.get(url('export'),{...config(),responseType:'blob'});const link=document.createElement('a');link.href=URL.createObjectURL(data);link.download=`${project.value.title}.pptx`;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)}catch(e){failure(e)}finally{busy.value=false}}
function prepareToLeave(){if(dirty.value){error.value=t('pptProject.unsaved');return false}return true}
function back(){if(prepareToLeave())router.push({name:'course-workspace',params:{courseId:props.courseId,mode:'build'}})}
watch(()=>props.courseId,()=>{contextVersion++;pollVersion++;controller.abort();controller=new AbortController();if(timer)clearTimeout(timer);project.value=null;catalog.value=null;step.value=1;page.value=0;error.value='';dirty.value=false;busy.value=false;lessonIds.value=props.initialLessonId?[props.initialLessonId]:[];assetIds.value=[];void loadCatalog()},{immediate:true})
watch(()=>props.sourceRevision,()=>{void loadCatalog();if(project.value && !dirty.value && !busy.value)void poll()})
function protectUnsaved(event:BeforeUnloadEvent){if(!dirty.value)return;event.preventDefault();event.returnValue=''}
onMounted(()=>window.addEventListener('beforeunload',protectUnsaved))
onBeforeUnmount(()=>{window.removeEventListener('beforeunload',protectUnsaved);disposed=true;controller.abort();if(timer)clearTimeout(timer)})
defineExpose({prepareToLeave, context, runContextAction, sources})
</script>
<style scoped>
.ppt-project-workspace{height:100%;min-height:540px;display:flex;flex-direction:column;overflow:auto;background:transparent;color:var(--lz-text-primary);font:inherit;letter-spacing:0}
.project-toolbar{min-height:70px;display:flex;align-items:center;gap:20px;padding:12px 24px;flex-shrink:0}
.project-title{flex:1;min-width:0}.project-title h2{margin:0;color:var(--lz-text-primary);font-size:24px;line-height:1.4}
.project-toolbar nav{display:flex;flex:1;justify-content:center}
.ppt-project-workspace button{font:inherit;font-size:15px;color:var(--lz-text-secondary);cursor:pointer;background:transparent;border:1px solid transparent;border-radius:7px;display:inline-flex;align-items:center;gap:8px;padding:8px 12px}
.ppt-project-workspace button:hover:not(:disabled){background:var(--lz-bg-page)}
.ppt-project-workspace button:focus-visible,.ppt-project-workspace input:focus-visible{outline:2px solid var(--lz-brand-strong);outline-offset:3px}
.ppt-project-workspace button:disabled{opacity:.45;cursor:not-allowed}
.project-selection{width:100%;max-width:1040px;margin:0 auto;box-sizing:border-box;padding:24px;flex:1}
.empty-copy{color:var(--lz-text-secondary);font-size:15px;margin:0}
.selection-columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:32px;margin:0 0 32px}
.selection-columns h2,.existing-projects h2{color:var(--lz-text-primary);font-size:17px;font-weight:600;margin:0 0 16px}
.source-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:40px;margin-top:-8px}.source-heading h2{margin:0}
.source-row{display:flex;align-items:center;gap:12px;min-height:52px;border-bottom:1px solid var(--lz-border);padding:8px 0;cursor:pointer}
.source-row input{width:16px;height:16px;accent-color:var(--lz-brand-strong);flex-shrink:0}.source-row span{flex:1;min-width:0;overflow-wrap:anywhere}.source-row small{color:var(--lz-text-secondary);font-size:14px}
.source-row.unavailable{color:var(--lz-text-secondary);cursor:default}.file-input{display:none}
.upload-area{display:flex!important;flex-direction:column;width:100%;min-height:126px;border:1px dashed var(--lz-border)!important;margin-top:12px;justify-content:center}
.upload-area strong{font-size:15px;font-weight:500}.upload-area span{font-size:13px}
.selection-footer{display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--lz-border);padding-top:20px;margin-top:28px;gap:24px}.selection-footer>span{font-size:15px;color:var(--lz-text-secondary)}
.ppt-project-workspace button.primary{background:var(--lz-brand-strong);color:#fff;padding:9px 18px}.ppt-project-workspace button.primary:hover:not(:disabled){filter:brightness(.94);background:var(--lz-brand-strong)}
.existing-projects{margin-top:32px}.existing-projects>button{display:flex;width:100%;border-bottom:1px solid var(--lz-border);border-radius:0;padding:12px 0;text-align:left}.existing-projects>button span{flex:1;min-width:0;overflow-wrap:anywhere}
.project-message{display:flex;align-items:center;gap:16px;padding:12px 24px;color:var(--lz-text-secondary);font-size:15px}.project-message.is-error{color:#922e2e;background:#fff4f1}
.project-progress{display:flex;align-items:center;gap:14px;padding:18px 24px}.project-progress progress{height:4px;width:140px;accent-color:var(--lz-brand-strong)}.project-progress button{margin-left:auto}
.project-empty{padding:48px 24px;color:var(--lz-text-secondary);text-align:center}
.project-render{padding:24px;flex:1;min-height:0;display:flex;flex-direction:column}.project-render>header{display:flex;align-items:center;gap:12px;margin-bottom:24px}.project-render>header>div{flex:1;min-width:0}.project-render h1{color:var(--lz-text-primary);font-size:20px;font-weight:600;margin:0 0 6px;overflow-wrap:anywhere}.project-render p{font-size:15px;color:var(--lz-text-secondary);margin:0}
.project-deck{display:grid;grid-template-columns:160px minmax(0,1fr);min-height:350px;gap:20px;margin-top:20px;flex:1}.project-deck>nav{overflow:auto}.project-deck>nav button{display:flex;width:100%;text-align:left;align-items:flex-start;margin-bottom:6px;overflow-wrap:anywhere}.project-deck>nav button span{color:var(--lz-text-secondary)}.project-deck>nav button.active{background:var(--lz-bg-page);color:var(--lz-brand-strong)}
.project-canvas{align-self:center;min-width:0;width:100%}
.spinning{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.spinning{animation:none}}
.ppt-project-workspace :deep(.ppt-manuscript-workflow){border:0;border-radius:0;box-shadow:none;flex:1;min-height:440px;background:transparent}
.ppt-project-workspace :deep(.ppt-manuscript-workflow__pages){min-height:420px}
@media(max-width:1100px){.selection-columns{grid-template-columns:minmax(0,1fr)}.project-toolbar{flex-wrap:wrap;gap:12px}.project-deck{grid-template-columns:120px minmax(0,1fr);gap:12px}}
</style>
