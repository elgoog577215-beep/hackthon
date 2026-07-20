<template>
  <aside class="course-navigator glass-panel-elevated" :aria-label="t('learningNavigator.title', '课程目录')">
    <header>
      <button type="button" :title="t('learningNavigator.back', '返回课程库')" @click="emit('back')">
        <ArrowLeft :size="16" />
      </button>
      <div v-if="productionMode && !courseStore.courseTree.length" class="navigator-production-label">
        <ListTree :size="14" />
        <span>{{ t('courseGeneration.production.navigatorLabel', '课程结构') }}</span>
      </div>
      <label v-else class="navigator-search">
        <Search :size="14" />
        <input v-model="query" type="search" :placeholder="t('learningNavigator.search', '查找章节或内容')" />
      </label>
      <button type="button" :title="t('learningNavigator.close', '收起目录')" @click="emit('close')">
        <PanelLeftClose :size="16" />
      </button>
    </header>

    <nav v-if="courseStore.courseTree.length">
      <ul>
      <CourseNavigatorNode
          v-for="node in courseStore.courseTree"
          :key="node.node_id"
          :node="node"
          :active-id="courseStore.currentNode?.node_id"
          :active-block-id="activeBlockId"
          :query="query"
          @select="emit('select', $event)"
          @select-block="emit('selectBlock', $event)"
        />
      </ul>
    </nav>
    <section v-else-if="productionMode" class="navigator-production-empty" :data-state="generationTask?.status || 'pending'">
      <span class="navigator-production-empty__icon">
        <TriangleAlert v-if="generationTask?.status === 'error' || generationTask?.status === 'conflict'" :size="18" />
        <CirclePause v-else-if="generationTask?.status === 'paused'" :size="18" />
        <LoaderCircle v-else :size="18" />
      </span>
      <strong>{{ navigatorTitle }}</strong>
      <p>{{ navigatorHelp }}</p>
      <div class="navigator-production-empty__progress" aria-hidden="true">
        <i :style="{ width: `${generationProgress}%` }"></i>
      </div>
      <small>{{ generationProgress }}%</small>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowLeft, CirclePause, ListTree, LoaderCircle, PanelLeftClose, Search, TriangleAlert } from 'lucide-vue-next'
import CourseNavigatorNode from './CourseNavigatorNode.vue'
import { useCourseStore } from '../stores/course'
import type { CourseBlockNavigationTarget, Node, Task } from '../stores/types'
import { t } from '../shared/i18n'

const props = withDefaults(defineProps<{
  activeBlockId?: string
  productionMode?: boolean
  generationTask?: Task
}>(), {
  activeBlockId: '',
  productionMode: false,
  generationTask: undefined,
})
const emit = defineEmits<{
  (event: 'select', node: Node): void
  (event: 'selectBlock', target: CourseBlockNavigationTarget): void
  (event: 'back' | 'close'): void
}>()
const courseStore = useCourseStore()
const query = ref('')
const generationProgress = computed(() => Math.max(0, Math.min(100, Math.round(Number(props.generationTask?.progress || 0)))))
const navigatorTitle = computed(() => {
  if (props.generationTask?.status === 'error') return t('courseGeneration.production.navigatorInterrupted', '课程结构生成中断')
  if (props.generationTask?.status === 'paused') return t('courseGeneration.production.navigatorPaused', '课程结构生成已暂停')
  if (props.generationTask?.status === 'conflict') return t('courseGeneration.production.navigatorBlocked', '课程结构需要对账')
  return t('courseGeneration.production.navigatorWorking', '目录正在形成')
})
const navigatorHelp = computed(() => {
  if (props.generationTask?.status === 'error' || props.generationTask?.status === 'paused') {
    return t('courseGeneration.production.navigatorSaved', '需求与完整检查点已保存；继续后，目录会在这里逐步出现。')
  }
  return t('courseGeneration.production.navigatorHelp', '章节与小节生成后会直接进入这里，成为课程与教案的共同导航。')
})
</script>

<style scoped>
.course-navigator { width:280px; height:100%; min-height:0; display:grid; grid-template-rows:auto minmax(0,1fr); overflow:hidden; border:1px solid rgba(255,255,255,.88); border-radius:20px; background:linear-gradient(160deg,rgba(255,255,255,.96),rgba(247,248,255,.91)); box-shadow:0 10px 30px rgba(79,70,229,.07),inset 0 1px 0 #fff; backdrop-filter:none; -webkit-backdrop-filter:none; }
.course-navigator > header { min-width:0; display:grid; grid-template-columns:32px minmax(0,1fr) 32px; align-items:center; gap:7px; padding:11px 10px 10px; border-bottom:1px solid rgba(224,231,255,.72); background:rgba(255,255,255,.42); }
.course-navigator header button { width:32px; height:32px; display:grid; place-items:center; border:1px solid transparent; border-radius:9px; color:var(--lz-text-muted); background:rgba(255,255,255,.36); cursor:pointer; transition:transform .16s ease,color .16s ease,background .16s ease,border-color .16s ease; }
.course-navigator header button:hover { transform:translateY(-1px); border-color:#e0e7ff; color:var(--lz-brand-strong); background:#fff; }
.navigator-search { height:34px; min-width:0; display:flex; align-items:center; gap:7px; margin:0; padding:0 10px; border:1px solid rgba(226,232,240,.82); border-radius:10px; color:var(--lz-text-muted); background:rgba(248,250,252,.78); transition:border-color .16s ease,background .16s ease,box-shadow .16s ease; }
.navigator-search:focus-within { border-color:#c4b5fd; background:#fff; box-shadow:0 0 0 3px rgba(139,92,246,.08); }
.navigator-search input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; font-size: 11px; }
.navigator-production-label { height:34px; min-width:0; display:flex; align-items:center; gap:7px; padding:0 10px; border:1px solid rgba(226,232,240,.82); border-radius:10px; color:#5552c9; background:#f7f7ff; font-size:10px; font-weight:750; }
.course-navigator nav { min-height:0; overflow-y:auto; padding:6px 8px 18px; scrollbar-width:thin; scrollbar-color:#dbe4f2 transparent; }
.course-navigator nav > ul { margin: 0; padding: 0; }
.navigator-production-empty { min-height:0; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:32px 28px 48px; text-align:center; }
.navigator-production-empty__icon { width:42px; height:42px; display:grid; place-items:center; margin-bottom:13px; border:1px solid #dedfff; border-radius:13px; color:#5a57dd; background:#f3f2ff; box-shadow:0 8px 22px rgba(79,70,229,.08); }
.navigator-production-empty[data-state="running"] .navigator-production-empty__icon svg,.navigator-production-empty[data-state="pending"] .navigator-production-empty__icon svg { animation:navigator-production-spin .9s linear infinite; }
.navigator-production-empty[data-state="error"] .navigator-production-empty__icon,.navigator-production-empty[data-state="conflict"] .navigator-production-empty__icon { border-color:#f1ce96; color:#b54708; background:#fff7e8; }
.navigator-production-empty[data-state="paused"] .navigator-production-empty__icon { border-color:#d0d5dd; color:#667085; background:#f2f4f7; }
.navigator-production-empty strong { color:#344054; font-size:12px; }
.navigator-production-empty p { margin:6px 0 16px; color:#8a93a4; font-size:9px; line-height:1.65; }
.navigator-production-empty__progress { width:100%; height:4px; overflow:hidden; border-radius:999px; background:#e9ebf4; }
.navigator-production-empty__progress i { display:block; height:100%; min-width:3px; border-radius:inherit; background:linear-gradient(90deg,#5a57dd,#938bf7); }
.navigator-production-empty[data-state="error"] .navigator-production-empty__progress i,.navigator-production-empty[data-state="conflict"] .navigator-production-empty__progress i { background:#d97706; }
.navigator-production-empty small { align-self:flex-end; margin-top:5px; color:#8a93a4; font:700 8px ui-monospace,SFMono-Regular,monospace; }
@keyframes navigator-production-spin { to { transform:rotate(360deg); } }
@media (prefers-reduced-motion:reduce) { .navigator-production-empty__icon svg { animation:none!important; } }
</style>
