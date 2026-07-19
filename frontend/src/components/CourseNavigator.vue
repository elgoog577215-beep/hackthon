<template>
  <aside class="course-navigator glass-panel-elevated" :aria-label="t('learningNavigator.title', '课程目录')">
    <header>
      <button type="button" :title="t('learningNavigator.back', '返回课程库')" @click="emit('back')">
        <ArrowLeft :size="16" />
      </button>
      <label class="navigator-search">
        <Search :size="14" />
        <input v-model="query" type="search" :placeholder="t('learningNavigator.search', '查找章节或内容')" />
      </label>
      <button type="button" :title="t('learningNavigator.close', '收起目录')" @click="emit('close')">
        <PanelLeftClose :size="16" />
      </button>
    </header>

    <nav>
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
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ArrowLeft, PanelLeftClose, Search } from 'lucide-vue-next'
import CourseNavigatorNode from './CourseNavigatorNode.vue'
import { useCourseStore } from '../stores/course'
import type { CourseBlockNavigationTarget, Node } from '../stores/types'
import { t } from '../shared/i18n'

withDefaults(defineProps<{ activeBlockId?: string }>(), { activeBlockId: '' })
const emit = defineEmits<{
  (event: 'select', node: Node): void
  (event: 'selectBlock', target: CourseBlockNavigationTarget): void
  (event: 'back' | 'close'): void
}>()
const courseStore = useCourseStore()
const query = ref('')
</script>

<style scoped>
.course-navigator { width:280px; height:100%; min-height:0; display:grid; grid-template-rows:auto minmax(0,1fr); overflow:hidden; border:1px solid rgba(255,255,255,.88); border-radius:20px; background:linear-gradient(160deg,rgba(255,255,255,.96),rgba(247,248,255,.91)); box-shadow:0 10px 30px rgba(79,70,229,.07),inset 0 1px 0 #fff; backdrop-filter:none; -webkit-backdrop-filter:none; }
.course-navigator > header { min-width:0; display:grid; grid-template-columns:32px minmax(0,1fr) 32px; align-items:center; gap:7px; padding:11px 10px 10px; border-bottom:1px solid rgba(224,231,255,.72); background:rgba(255,255,255,.42); }
.course-navigator header button { width:32px; height:32px; display:grid; place-items:center; border:1px solid transparent; border-radius:9px; color:var(--lz-text-muted); background:rgba(255,255,255,.36); cursor:pointer; transition:transform .16s ease,color .16s ease,background .16s ease,border-color .16s ease; }
.course-navigator header button:hover { transform:translateY(-1px); border-color:#e0e7ff; color:var(--lz-brand-strong); background:#fff; }
.navigator-search { height:34px; min-width:0; display:flex; align-items:center; gap:7px; margin:0; padding:0 10px; border:1px solid rgba(226,232,240,.82); border-radius:10px; color:var(--lz-text-muted); background:rgba(248,250,252,.78); transition:border-color .16s ease,background .16s ease,box-shadow .16s ease; }
.navigator-search:focus-within { border-color:#c4b5fd; background:#fff; box-shadow:0 0 0 3px rgba(139,92,246,.08); }
.navigator-search input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; font-size: 11px; }
.course-navigator nav { min-height:0; overflow-y:auto; padding:6px 8px 18px; scrollbar-width:thin; scrollbar-color:#dbe4f2 transparent; }
.course-navigator nav > ul { margin: 0; padding: 0; }
</style>
