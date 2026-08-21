<template>
  <li
    class="workspace-folder-node"
    role="treeitem"
    :aria-expanded="hasChildren ? expanded : undefined"
    :aria-selected="currentId === node.id"
  >
    <div class="workspace-folder-node__row" :class="{ current: currentId === node.id }">
      <button
        v-if="hasChildren"
        type="button"
        class="workspace-folder-node__toggle"
        :aria-label="expanded ? t('courseFiles.collapseFolder') : t('courseFiles.expandFolder')"
        @click.stop="emit('toggle', node.id)"
      >
        <ChevronRight :size="13" :class="{ expanded }" />
      </button>
      <span v-else class="workspace-folder-node__indent" aria-hidden="true" />
      <button type="button" class="workspace-folder-node__label" @click="selectFolder">
        <FolderOpen v-if="expanded" :size="15" />
        <Folder v-else :size="15" />
        <strong>{{ node.label }}</strong>
        <i v-if="node.attention" :title="t('courseFiles.updateNeeded')" />
      </button>
    </div>
    <ul v-if="hasChildren && expanded" role="group">
      <WorkspaceFolderTreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :current-id="currentId"
        :expanded-ids="expandedIds"
        @select="emit('select', $event)"
        @toggle="emit('toggle', $event)"
      />
    </ul>
  </li>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChevronRight, Folder, FolderOpen } from 'lucide-vue-next'
import { t } from '../shared/i18n'

type WorkspaceFolderTreeItem = {
  id: string
  label: string
  attention?: boolean
  children?: WorkspaceFolderTreeItem[]
}

const props = defineProps<{
  node: WorkspaceFolderTreeItem
  currentId: string
  expandedIds: string[]
}>()
const emit = defineEmits<{
  (event: 'select', id: string): void
  (event: 'toggle', id: string): void
}>()

const hasChildren = computed(() => Boolean(props.node.children?.length))
const expanded = computed(() => props.expandedIds.includes(props.node.id))

function selectFolder() {
  emit('select', props.node.id)
}
</script>

<style scoped>
.workspace-folder-node,.workspace-folder-node ul{margin:0;padding:0;list-style:none}.workspace-folder-node ul{margin-left:19px}.workspace-folder-node__row{height:38px;display:grid;grid-template-columns:20px minmax(0,1fr);align-items:center;border-radius:7px}.workspace-folder-node__row:hover{background:#eef2f7}.workspace-folder-node__row.current{background:#e8edff}.workspace-folder-node__toggle{width:20px;height:34px;display:grid;place-items:center;padding:0;border:0;color:#64748b;background:transparent;cursor:pointer}.workspace-folder-node__toggle svg{transition:transform .16s ease}.workspace-folder-node__toggle svg.expanded{transform:rotate(90deg)}.workspace-folder-node__indent{width:20px}.workspace-folder-node__label{min-width:0;height:38px;display:grid;grid-template-columns:20px minmax(0,1fr) auto;align-items:center;gap:7px;padding:0 8px 0 0;border:0;color:#475569;background:transparent;text-align:left;cursor:pointer}.workspace-folder-node__label svg{color:#64748b}.workspace-folder-node__row.current .workspace-folder-node__label,.workspace-folder-node__row.current .workspace-folder-node__label svg{color:#3730a3}.workspace-folder-node__label strong{overflow:hidden;font-size:13px;font-weight:650;text-overflow:ellipsis;white-space:nowrap}.workspace-folder-node__label i{width:7px;height:7px;border-radius:50%;background:#f97316}
</style>
