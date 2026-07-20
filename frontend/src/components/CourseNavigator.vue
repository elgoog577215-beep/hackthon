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
      <header>
        <strong>{{ t('courseGeneration.production.navigatorLabel', '课程结构') }}</strong>
        <span>{{ generationProgress }}%</span>
      </header>
      <ol class="navigator-production-skeleton" aria-hidden="true">
        <li v-for="row in skeletonRows" :key="row" :data-level="row === 1 || row === 4 ? 1 : 2">
          <i></i>
          <span></span>
          <b></b>
        </li>
      </ol>
      <footer>
        <TriangleAlert v-if="generationTask?.status === 'error' || generationTask?.status === 'conflict'" :size="14" />
        <CirclePause v-else-if="generationTask?.status === 'paused'" :size="14" />
        <LoaderCircle v-else :size="14" />
        <div>
          <strong>{{ navigatorTitle }}</strong>
          <p>{{ navigatorHelp }}</p>
        </div>
      </footer>
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
const skeletonRows = [1, 2, 3, 4, 5, 6]
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
.navigator-production-empty { min-height:0; display:grid; grid-template-rows:auto minmax(0,1fr) auto; padding:10px 14px 15px; text-align:left; }
.navigator-production-empty > header { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:7px 2px 11px; border-bottom:1px solid #e8ebf0; }
.navigator-production-empty > header strong { color:#4b5567; font-size:9px; }
.navigator-production-empty > header span { color:#777f8f; font:700 8px/1 ui-monospace,SFMono-Regular,monospace; }
.navigator-production-skeleton { display:grid; align-content:start; margin:0; padding:7px 0; list-style:none; }
.navigator-production-skeleton li { display:grid; grid-template-columns:16px 10px minmax(0,1fr); align-items:center; gap:7px; min-height:38px; padding:5px 3px; border-bottom:1px solid #f1f2f5; }
.navigator-production-skeleton li > i { width:12px; height:5px; border-radius:2px; background:#e9ecf1; }
.navigator-production-skeleton li > span { width:8px; height:8px; border:1px solid #d6dbe3; border-radius:50%; background:#fff; }
.navigator-production-skeleton li[data-level="1"] > span { width:10px; height:10px; border:0; border-radius:3px; background:#d4d9e1; }
.navigator-production-skeleton li > b { width:72%; height:8px; border-radius:3px; background:linear-gradient(90deg,#e9ecf1 20%,#f7f8fa 45%,#e9ecf1 70%); background-size:220% 100%; animation:navigator-production-shimmer 1.5s ease infinite; }
.navigator-production-skeleton li:nth-child(2) > b,.navigator-production-skeleton li:nth-child(5) > b { width:88%; }
.navigator-production-empty > footer { display:grid; grid-template-columns:22px minmax(0,1fr); align-items:start; gap:7px; padding:10px 9px; border:1px solid #e1e4eb; border-radius:8px; color:#5a61bf; background:#f8f8fd; }
.navigator-production-empty > footer > svg { margin-top:1px; }
.navigator-production-empty[data-state="running"] > footer > svg,.navigator-production-empty[data-state="pending"] > footer > svg { animation:navigator-production-spin .9s linear infinite; }
.navigator-production-empty[data-state="error"] > footer,.navigator-production-empty[data-state="conflict"] > footer { border-color:#efd4aa; color:#b54708; background:#fff9ef; }
.navigator-production-empty[data-state="paused"] > footer { border-color:#d9dde4; color:#667085; background:#f5f6f8; }
.navigator-production-empty > footer strong { display:block; color:currentColor; font-size:9px; }
.navigator-production-empty > footer p { margin:2px 0 0; color:#838b99; font-size:8px; line-height:1.45; }
@keyframes navigator-production-spin { to { transform:rotate(360deg); } }
@keyframes navigator-production-shimmer { to { background-position:-220% 0; } }
@media (prefers-reduced-motion:reduce) { .navigator-production-empty svg,.navigator-production-skeleton b { animation:none!important; } }
</style>
