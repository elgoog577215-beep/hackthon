<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="courseStore.showKnowledgeGraph" class="kg-overlay" @click.self="handleClose">
        <div class="kg-container">
          <!-- 头部工具栏 -->
          <div class="kg-header">
            <div class="kg-header-left">
              <div class="kg-icon-wrap"><el-icon :size="16"><Share /></el-icon></div>
              <span class="kg-title">知识图谱</span>
            </div>

            <div class="kg-header-center" v-if="hasGraph">
              <div class="kg-search-wrap">
                <el-icon class="kg-search-ico"><Search /></el-icon>
                <input v-model="searchQuery" placeholder="搜索概念..." class="kg-search-input"
                  @input="handleSearchInput" @keyup.enter="handleSearch" />
                <button v-if="searchQuery" class="kg-search-clear" @click="clearSearch">
                  <el-icon><Close /></el-icon>
                </button>
              </div>
            </div>

            <div class="kg-header-right">
              <template v-if="hasGraph">
                <!-- 连线模式 -->
                <button class="kg-hbtn" :class="{ 'kg-hbtn--active': linkMode }" @click="toggleLinkMode">
                  <el-icon><Connection /></el-icon>
                  {{ linkMode ? '取消连线' : '连线' }}
                </button>
                <button class="kg-hbtn" @click="handleAddNode">
                  <el-icon><Plus /></el-icon> 添加节点
                </button>
                <button class="kg-hbtn" @click="handleGenerate" :disabled="loading">
                  <el-icon :class="{ 'is-loading': loading }"><Refresh /></el-icon> AI 生成
                </button>
                <button class="kg-hbtn" @click="canvasRef?.fitView()">
                  <el-icon><FullScreen /></el-icon> 重置
                </button>
                <button class="kg-hbtn" @click="handleExport">
                  <el-icon><Download /></el-icon> 导出
                </button>
              </template>
              <button v-if="!hasGraph && !loading" class="kg-btn-primary" @click="handleGenerate">
                <el-icon><MagicStick /></el-icon> 生成图谱
              </button>
              <button class="kg-close" @click="handleClose"><el-icon :size="16"><Close /></el-icon></button>
            </div>
          </div>

          <!-- 主体 -->
          <div class="kg-body">
            <KGCanvas
              ref="canvasRef"
              :nodes="graphData.nodes"
              :edges="graphData.edges"
              :selected-node-id="selectedNode?.id ?? null"
              :selected-edge-id="selectedEdge?.id ?? null"
              :show-edge-labels="showEdgeLabels"
              :loading="loading"
              :link-mode="linkMode"
              :link-source="linkSource"
              :pending-node-ids="pendingKgNodeIds"
              @select-node="selectNode"
              @select-edge="selectEdge"
              @deselect-all="deselectAll"
              @node-position-changed="handleNodePositionChanged"
              @generate="handleGenerate"
              @add-node="handleAddNode"
              @link-target="handleLinkTarget"
            />

            <!-- 图例 -->
            <div v-if="hasGraph" class="kg-legend">
              <div class="kg-legend-title">图例</div>
              <div class="kg-legend-items">
                <div v-for="t in nodeTypesForLegend" :key="t.value" class="kg-legend-item">
                  <span class="kg-legend-dot" :style="{ background: t.color }"></span>
                  <span class="kg-legend-label">{{ t.label }}</span>
                </div>
              </div>
              <button class="kg-legend-toggle" @click="showEdgeLabels = !showEdgeLabels">
                {{ showEdgeLabels ? '隐藏' : '显示' }}关系标签
              </button>
            </div>

            <!-- 缩放控件 -->
            <div v-if="hasGraph" class="kg-zoom">
              <button class="kg-zbtn" @click="canvasRef?.zoomIn()"><el-icon><Plus /></el-icon></button>
              <span class="kg-zlevel">{{ zoomLevel }}%</span>
              <button class="kg-zbtn" @click="canvasRef?.zoomOut()"><el-icon><Minus /></el-icon></button>
            </div>

            <!-- 统计 -->
            <div v-if="hasGraph" class="kg-stats">
              {{ graphData.nodes.length }} 个节点 · {{ graphData.edges.length }} 条关系
              <span v-if="userNodeCount > 0" class="kg-stats-user">（{{ userNodeCount }} 个手动创建）</span>
            </div>

            <!-- 连线模式提示 -->
            <div v-if="linkMode" class="kg-link-hint">
              <span v-if="!linkSource">🔗 点击源节点开始连线</span>
              <span v-else>🔗 点击目标节点完成连线（{{ linkSource.label }} → ?）</span>
            </div>

            <!-- 选中边的操作栏 -->
            <div v-if="selectedEdge && !selectedNode" class="kg-edge-actions">
              <span class="kg-ea-label">{{ getEdgeDisplayLabel(selectedEdge) }}</span>
              <span class="kg-ea-weight">权重: {{ selectedEdge.weight ?? 5 }}</span>
              <button class="kg-ea-btn" @click="handleEditEdge(selectedEdge)">
                <el-icon :size="12"><Edit /></el-icon> 编辑
              </button>
              <button class="kg-ea-btn kg-ea-btn--danger" @click="handleDeleteEdge(selectedEdge)">
                <el-icon :size="12"><Delete /></el-icon> 删除
              </button>
            </div>

            <!-- 详情面板 -->
            <KGDetailPanel
              :node="selectedNode"
              :related-nodes="relatedNodes"
              :notes="nodeNotes"
              :wrong-answers="nodeWrongAnswers"
              @close="deselectAll"
              @select-node="selectNode"
              @edit-node="handleEditNode"
              @delete-node="handleDeleteNode"
              @navigate-to-node="navigateToNode"
            >
              <!-- AI 待确认变更叠加层（知识图谱节点联动） -->
              <PendingChangeOverlay
                v-if="selectedNode"
                :node-id="selectedNode.id"
                node-kind="kg_node"
              />
            </KGDetailPanel>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 编辑器弹窗 -->
  <KGNodeEditor
    :visible="nodeEditorVisible"
    :node="editingNode"
    @close="nodeEditorVisible = false"
    @confirm="handleNodeEditorConfirm"
  />
  <KGEdgeEditor
    :visible="edgeEditorVisible"
    :edge="editingEdge"
    :source-node="edgeEditorSource"
    :target-node="edgeEditorTarget"
    @close="closeEdgeEditor"
    @confirm="handleEdgeEditorConfirm"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useCourseStore } from '../stores/course'
import { useNoteStore } from '../stores/notes'
import { useReviewStore } from '../stores/review'
import { usePendingChangesStore } from '../stores/pendingChanges'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Share, Search, Close, MagicStick, Refresh, Download,
  Plus, Minus, FullScreen, Connection, Edit, Delete,
} from '@element-plus/icons-vue'
import http from '../utils/http'
import logger from '../utils/logger'
import {
  NODE_TYPES, getRelationLabel,
  type KGNode, type KGEdge, type KnowledgeGraphData,
} from '../types/knowledge-graph'
import KGCanvas from './knowledge-graph/KGCanvas.vue'
import KGDetailPanel from './knowledge-graph/KGDetailPanel.vue'
import KGNodeEditor from './knowledge-graph/KGNodeEditor.vue'
import KGEdgeEditor from './knowledge-graph/KGEdgeEditor.vue'
import PendingChangeOverlay from './PendingChangeOverlay.vue'

const courseStore = useCourseStore()
const noteStore = useNoteStore()
const reviewStore = useReviewStore()
const pendingChangesStore = usePendingChangesStore()

// --- Core state ---
const loading = ref(false)
const graphData = ref<KnowledgeGraphData>({ nodes: [], edges: [], updated_at: 0 })
const selectedNode = ref<KGNode | null>(null)
const selectedEdge = ref<KGEdge | null>(null)
const searchQuery = ref('')
const showEdgeLabels = ref(false)
const canvasRef = ref<InstanceType<typeof KGCanvas> | null>(null)

// --- Link mode ---
const linkMode = ref(false)
const linkSource = ref<KGNode | null>(null)

// --- Editors ---
const nodeEditorVisible = ref(false)
const editingNode = ref<KGNode | null>(null)
const edgeEditorVisible = ref(false)
const editingEdge = ref<KGEdge | null>(null)
const edgeEditorSource = ref<KGNode | null>(null)
const edgeEditorTarget = ref<KGNode | null>(null)

// --- Pending position saves ---
const pendingPositions = ref<Record<string, { x: number; y: number }>>({})
let positionSaveTimer: ReturnType<typeof setTimeout> | null = null

// --- Computed ---
const hasGraph = computed(() => graphData.value.nodes.length > 0)
const zoomLevel = computed(() => canvasRef.value?.getZoomLevel() ?? 100)
const userNodeCount = computed(() => graphData.value.nodes.filter(n => n.created_by === 'user').length)
const nodeTypesForLegend = NODE_TYPES

/** 存在待确认知识图谱联动变更的节点 id 集合，供画布高亮 */
const pendingKgNodeIds = computed<Set<string>>(() => {
  const ids = new Set<string>()
  graphData.value.nodes.forEach(n => {
    if (pendingChangesStore.pendingForKgNode(n.id).length > 0) ids.add(n.id)
  })
  return ids
})

const apiBase = computed(() => `/api/courses/${courseStore.currentCourseId}/knowledge_graph`)

const relatedNodes = computed(() => {
  if (!selectedNode.value) return []
  const id = selectedNode.value.id
  const out: { node: KGNode; relation: string; weight: number }[] = []
  graphData.value.edges.forEach(e => {
    if (e.source === id) {
      const n = graphData.value.nodes.find(n => n.id === e.target)
      if (n) out.push({ node: n, relation: e.relation, weight: e.weight ?? 5 })
    } else if (e.target === id) {
      const n = graphData.value.nodes.find(n => n.id === e.source)
      if (n) out.push({ node: n, relation: e.relation, weight: e.weight ?? 5 })
    }
  })
  return out.slice(0, 8)
})

// 收集选中节点关联的课程节点 ID
const selectedNodeIds = computed<Set<string>>(() => {
  if (!selectedNode.value?.chapter_id) return new Set()
  const cid = selectedNode.value.chapter_id
  const ids = new Set<string>([cid])
  if (selectedNode.value.type === 'root' || selectedNode.value.type === 'custom') {
    const allNodes = courseStore.getLinearNodes(courseStore.courseTree)
    const collectChildren = (parentId: string) => {
      for (const n of allNodes) {
        if (n.parent_node_id === parentId && !ids.has(n.node_id)) {
          ids.add(n.node_id)
          collectChildren(n.node_id)
        }
      }
    }
    collectChildren(cid)
  }
  return ids
})

const nodeNotes = computed(() => {
  const ids = selectedNodeIds.value
  if (ids.size === 0) return []
  return noteStore.notes
    .filter((n: any) => ids.has(n.nodeId) && n.sourceType !== 'format')
    .sort((a: any, b: any) => b.createdAt - a.createdAt)
    .slice(0, 5)
})

const nodeWrongAnswers = computed(() => {
  const ids = selectedNodeIds.value
  if (ids.size === 0) return []
  return reviewStore.wrongAnswers
    .filter((w: any) => ids.has(w.nodeId))
    .sort((a: any, b: any) => b.timestamp - a.timestamp)
    .slice(0, 5)
})

const getEdgeDisplayLabel = (edge: KGEdge) => edge.label || getRelationLabel(edge.relation)

/** 根据节点坐标直接设置 canvas viewBox，不依赖 DOM 尺寸 */
const setViewBoxFromNodes = (nodes: KGNode[]) => {
  if (!nodes.length || !canvasRef.value?.vb) return
  const pad = 150
  const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const w = Math.max(maxX - minX + pad * 2, 1000)
  const h = Math.max(maxY - minY + pad * 2, 600)
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  canvasRef.value.vb.x = cx - w / 2
  canvasRef.value.vb.y = cy - h / 2
  canvasRef.value.vb.width = w
  canvasRef.value.vb.height = h
}

// --- Layout ---
const layoutGraph = () => {
  const { nodes, edges } = graphData.value
  if (!nodes.length) return

  // 确保所有节点都有数值坐标（后端数据可能缺少 x/y）
  nodes.forEach(n => {
    if (typeof n.x !== 'number' || isNaN(n.x)) n.x = 0
    if (typeof n.y !== 'number' || isNaN(n.y)) n.y = 0
  })

  // 如果节点已有非零坐标（持久化的），使用已有位置，直接 fitView
  const hasPositions = nodes.some(n => n.x !== 0 || n.y !== 0)
  if (hasPositions) {
    // 立即根据节点坐标设置 viewBox（不依赖 DOM 尺寸）
    setViewBoxFromNodes(nodes)
    nextTick(() => {
      canvasRef.value?.fitView()
    })
    return
  }

  // --- 初始位置：以根节点为中心，BFS 层级环形分布 ---
  const adj: Record<string, string[]> = {}
  nodes.forEach(n => { adj[n.id] = [] })
  edges.forEach(e => {
    adj[e.source]?.push(e.target)
    adj[e.target]?.push(e.source)
  })

  const root = nodes.find(n => n.type === 'root') ?? nodes[0]
  if (!root) return
  const level: Record<string, number> = {}
  const q = [root.id]
  level[root.id] = 0
  const visited = new Set([root.id])
  while (q.length) {
    const id = q.shift()!
    for (const c of adj[id] ?? []) {
      if (!visited.has(c)) { visited.add(c); level[c] = (level[id] ?? 0) + 1; q.push(c) }
    }
  }
  nodes.forEach(n => { if (level[n.id] === undefined) level[n.id] = (Math.max(0, ...Object.values(level)) + 1) })

  const groups: Record<number, KGNode[]> = {}
  nodes.forEach(n => { const l = level[n.id] ?? 0; (groups[l] ??= []).push(n) })
  const RING_GAP = 200
  root.x = 0; root.y = 0
  Object.keys(groups).map(Number).sort((a, b) => a - b).forEach(l => {
    if (l === 0) return
    const g = groups[l]
    if (!g) return
    const radius = l * RING_GAP
    g.forEach((n, i) => {
      const angle = (2 * Math.PI * i) / g.length - Math.PI / 2
      n.x = radius * Math.cos(angle)
      n.y = radius * Math.sin(angle)
    })
  })

  // 初始位置设好后，立即 fitView 居中显示，然后启动力模拟微调
  setViewBoxFromNodes(nodes)
  nextTick(() => {
    canvasRef.value?.fitView()
    canvasRef.value?.heatSimulation(0.8)
  })
}

// --- API calls ---
const loadGraph = async () => {
  if (!courseStore.currentCourseId) return
  try {
    const res = await http.get(apiBase.value)
    if (res.data.status === 'success' && res.data.data.nodes?.length) {
      graphData.value = res.data.data
      layoutGraph()
    }
  } catch (e) { logger.error(e) }
}

const handleGenerate = async () => {
  if (!courseStore.currentCourseId) { ElMessage.warning('请先选择课程'); return }
  loading.value = true
  try {
    const res = await http.post(`${apiBase.value}/generate`)
    if (res.data.status === 'success') {
      graphData.value = res.data.data
      layoutGraph()
      ElMessage.success('知识图谱生成成功')
    } else {
      ElMessage.error('生成失败：' + (res.data.message ?? '未知错误'))
    }
  } catch (e: any) {
    ElMessage.error('生成失败：' + (e.message ?? '网络错误'))
  } finally { loading.value = false }
}

// --- Node CRUD ---
const handleAddNode = () => {
  editingNode.value = null
  nodeEditorVisible.value = true
}

const handleEditNode = (node: KGNode) => {
  editingNode.value = node
  nodeEditorVisible.value = true
}

const handleNodeEditorConfirm = async (data: { label: string; type: string; description: string; color?: string }) => {
  if (!courseStore.currentCourseId) return
  try {
    if (editingNode.value) {
      // 更新
      const res = await http.put(`${apiBase.value}/nodes/${editingNode.value.id}`, data)
      if (res.data.status === 'success') {
        Object.assign(editingNode.value, res.data.data)
        ElMessage.success('节点已更新')
      }
    } else {
      // 创建 — 将新节点放在当前视口中心
      const res = await http.post(`${apiBase.value}/nodes`, data)
      if (res.data.status === 'success') {
        const newNode = res.data.data as KGNode
        // 设置初始位置为视口中心，避免出现在 (0,0) 远离可见区域
        if (canvasRef.value?.vb) {
          const v = canvasRef.value.vb
          newNode.x = v.x + v.width / 2 + (Math.random() - 0.5) * 60
          newNode.y = v.y + v.height / 2 + (Math.random() - 0.5) * 60
        }
        graphData.value.nodes.push(newNode)
        ElMessage.success('节点已创建')
      }
    }
  } catch (e: any) {
    ElMessage.error(e.message ?? '操作失败')
  }
  nodeEditorVisible.value = false
}

const handleDeleteNode = async (node: KGNode) => {
  try {
    await ElMessageBox.confirm(`确定删除节点「${node.label}」？关联的关系也会被删除。`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }

  try {
    const res = await http.delete(`${apiBase.value}/nodes/${node.id}`)
    if (res.data.status === 'success') {
      graphData.value.nodes = graphData.value.nodes.filter(n => n.id !== node.id)
      graphData.value.edges = graphData.value.edges.filter(e => e.source !== node.id && e.target !== node.id)
      if (selectedNode.value?.id === node.id) selectedNode.value = null
      ElMessage.success('节点已删除')
    }
  } catch (e: any) { ElMessage.error(e.message ?? '删除失败') }
}

// --- Edge CRUD ---
const handleEditEdge = (edge: KGEdge) => {
  editingEdge.value = edge
  edgeEditorSource.value = graphData.value.nodes.find(n => n.id === edge.source) ?? null
  edgeEditorTarget.value = graphData.value.nodes.find(n => n.id === edge.target) ?? null
  edgeEditorVisible.value = true
}

const handleDeleteEdge = async (edge: KGEdge) => {
  try {
    await ElMessageBox.confirm('确定删除这条关系？', '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }

  try {
    const res = await http.delete(`${apiBase.value}/edges/${edge.id}`)
    if (res.data.status === 'success') {
      graphData.value.edges = graphData.value.edges.filter(e => e.id !== edge.id)
      if (selectedEdge.value?.id === edge.id) selectedEdge.value = null
      ElMessage.success('关系已删除')
    }
  } catch (e: any) { ElMessage.error(e.message ?? '删除失败') }
}

const handleEdgeEditorConfirm = async (data: { relation: string; weight: number; label?: string }) => {
  if (!courseStore.currentCourseId) return
  try {
    if (editingEdge.value) {
      // 更新
      const res = await http.put(`${apiBase.value}/edges/${editingEdge.value.id}`, data)
      if (res.data.status === 'success') {
        Object.assign(editingEdge.value, res.data.data)
        ElMessage.success('关系已更新')
        // 权重变化后升温，让力模拟重新平衡
        canvasRef.value?.heatSimulation(0.4)
      }
    } else if (edgeEditorSource.value && edgeEditorTarget.value) {
      // 创建
      const res = await http.post(`${apiBase.value}/edges`, {
        source: edgeEditorSource.value.id,
        target: edgeEditorTarget.value.id,
        ...data,
      })
      if (res.data.status === 'success') {
        graphData.value.edges.push(res.data.data)
        ElMessage.success('关系已创建')
      }
    }
  } catch (e: any) { ElMessage.error(e.message ?? '操作失败') }
  closeEdgeEditor()
}

const closeEdgeEditor = () => {
  edgeEditorVisible.value = false
  editingEdge.value = null
  edgeEditorSource.value = null
  edgeEditorTarget.value = null
}

// --- Link mode ---
const toggleLinkMode = () => {
  linkMode.value = !linkMode.value
  linkSource.value = null
  if (linkMode.value) {
    selectedNode.value = null
    selectedEdge.value = null
  }
}

const handleLinkTarget = (targetNode: KGNode) => {
  if (!linkSource.value) {
    linkSource.value = targetNode
    return
  }
  if (linkSource.value.id === targetNode.id) {
    ElMessage.warning('不能连接到自身')
    return
  }
  // 检查是否已存在
  const exists = graphData.value.edges.some(
    e => e.source === linkSource.value!.id && e.target === targetNode.id
  )
  if (exists) {
    ElMessage.warning('这两个节点之间已有关系')
    linkSource.value = null
    return
  }
  // 打开边编辑器
  editingEdge.value = null
  edgeEditorSource.value = linkSource.value
  edgeEditorTarget.value = targetNode
  edgeEditorVisible.value = true
  linkSource.value = null
  linkMode.value = false
}

// --- Position persistence (debounced) ---
const handleNodePositionChanged = (nodeId: string, x: number, y: number) => {
  pendingPositions.value[nodeId] = { x, y }
  if (positionSaveTimer) clearTimeout(positionSaveTimer)
  positionSaveTimer = setTimeout(flushPositions, 2000)
}

const flushPositions = async () => {
  const positions = { ...pendingPositions.value }
  pendingPositions.value = {}
  if (!courseStore.currentCourseId || Object.keys(positions).length === 0) return
  try {
    await http.put(apiBase.value, { positions })
  } catch (e) { logger.error('Failed to save positions', e) }
}

// --- Selection ---
const selectNode = (node: KGNode) => {
  selectedNode.value = node
  selectedEdge.value = null
}

const selectEdge = (edge: KGEdge) => {
  selectedEdge.value = edge
  selectedNode.value = null
}

const deselectAll = () => {
  selectedNode.value = null
  selectedEdge.value = null
}

// --- Search ---
const handleSearchInput = () => {
  // 搜索高亮由 canvas 内部处理，这里只做回车定位
}

const handleSearch = () => {
  const q = searchQuery.value.toLowerCase()
  const found = graphData.value.nodes.find(n => n.label?.toLowerCase().includes(q))
  if (found) {
    selectNode(found)
    canvasRef.value?.focusNode(found)
  } else {
    ElMessage.info('未找到匹配节点')
  }
}

const clearSearch = () => { searchQuery.value = '' }

// --- Navigation ---
const navigateToNode = async (nodeId: string) => {
  // 先关闭弹窗，等 DOM 稳定后再触发滚动，避免布局重排导致偏移计算不准
  handleClose()
  // 等待弹窗关闭动画和 DOM 重排完成
  await new Promise(r => setTimeout(r, 150))
  courseStore.scrollToNode(nodeId)
  ElMessage.success('已跳转到对应章节')
}

// --- Export ---
const handleExport = () => {
  const el = canvasRef.value?.getCanvasElement()
  if (!el) return
  const svg = el.querySelector('svg')
  if (!svg) return
  let src = new XMLSerializer().serializeToString(svg)
  if (!src.includes('xmlns=')) src = src.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"')
  const url = URL.createObjectURL(new Blob([src], { type: 'image/svg+xml' }))
  const a = document.createElement('a')
  a.href = url; a.download = `kg-${courseStore.currentCourseId}.svg`
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 100)
  ElMessage.success('已导出 SVG')
}

// --- Close ---
const handleClose = async () => {
  canvasRef.value?.stopSimulation()
  await flushPositions()
  courseStore.showKnowledgeGraph = false
}

// --- Keyboard ---
const handleKeydown = (e: KeyboardEvent) => {
  if (!courseStore.showKnowledgeGraph) return
  if (e.key === 'Escape') {
    if (linkMode.value) { linkMode.value = false; linkSource.value = null }
    else if (selectedNode.value || selectedEdge.value) deselectAll()
    else handleClose()
  }
}

// --- Watchers ---
watch(() => courseStore.showKnowledgeGraph, show => {
  if (show) {
    loadGraph()
    if (courseStore.currentCourseId) {
      pendingChangesStore.fetchPendingChanges(courseStore.currentCourseId)
    }
    document.addEventListener('keydown', handleKeydown)
  } else {
    document.removeEventListener('keydown', handleKeydown)
    deselectAll()
    searchQuery.value = ''
    linkMode.value = false
    linkSource.value = null
  }
})

watch(() => courseStore.currentCourseId, () => {
  if (courseStore.showKnowledgeGraph) loadGraph()
})
</script>

<style scoped>
/* === Obsidian-style dark theme === */
.kg-overlay { position: fixed; inset: 0; z-index: 100; background: rgba(10,11,20,0.6); backdrop-filter: blur(6px); display: flex; align-items: center; justify-content: center; padding: 24px; }
.kg-container { width: 100%; height: 100%; max-width: 1400px; max-height: 900px; background: #1a1b2e; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.5); display: flex; flex-direction: column; overflow: hidden; border: 1px solid #2d2f4a; }
.kg-header { display: flex; align-items: center; gap: 14px; padding: 11px 18px; border-bottom: 1px solid #2d2f4a; background: #1e1f36; flex-shrink: 0; }
.kg-header-left { display: flex; align-items: center; gap: 9px; }
.kg-icon-wrap { width: 32px; height: 32px; border-radius: 8px; background: linear-gradient(135deg,#6366f1,#8b5cf6); display: flex; align-items: center; justify-content: center; color: #fff; }
.kg-title { font-size: 14px; font-weight: 700; color: #c4c9e2; }
.kg-header-center { flex: 1; max-width: 340px; }
.kg-search-wrap { position: relative; display: flex; align-items: center; }
.kg-search-ico { position: absolute; left: 9px; color: #6b7094; font-size: 13px; }
.kg-search-input { width: 100%; padding: 6px 30px 6px 30px; border: 1px solid #2d2f4a; border-radius: 9px; font-size: 12px; color: #c4c9e2; background: #232541; transition: all .2s; }
.kg-search-input:focus { outline: none; border-color: #6366f1; background: #282a4a; box-shadow: 0 0 0 3px rgba(99,102,241,.15); }
.kg-search-input::placeholder { color: #6b7094; }
.kg-search-clear { position: absolute; right: 7px; background: none; border: none; color: #6b7094; cursor: pointer; padding: 2px; display: flex; border-radius: 4px; }
.kg-search-clear:hover { color: #a78bfa; background: #2d2f4a; }
.kg-header-right { display: flex; align-items: center; gap: 5px; margin-left: auto; }
.kg-hbtn { display: inline-flex; align-items: center; gap: 4px; padding: 5px 10px; border-radius: 7px; border: 1px solid #2d2f4a; background: #232541; font-size: 12px; font-weight: 500; color: #8b8fa3; cursor: pointer; transition: all .15s; }
.kg-hbtn:hover:not(:disabled) { background: #2d2f4a; color: #c4c9e2; border-color: #3d4167; }
.kg-hbtn:disabled { opacity: .4; cursor: not-allowed; }
.kg-hbtn--active { background: rgba(99,102,241,.15); border-color: #6366f1; color: #a78bfa; font-weight: 600; }
.kg-btn-primary { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 9px; border: none; background: linear-gradient(135deg,#6366f1,#8b5cf6); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; box-shadow: 0 3px 16px rgba(99,102,241,.35); transition: all .2s; }
.kg-btn-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 5px 20px rgba(99,102,241,.5); }
.kg-btn-primary:disabled { opacity: .45; cursor: not-allowed; }
.kg-close { width: 32px; height: 32px; border-radius: 8px; border: 1px solid #2d2f4a; background: #232541; color: #6b7094; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s; }
.kg-close:hover { background: rgba(239,68,68,.15); color: #f87171; border-color: rgba(239,68,68,.3); }
.kg-body { flex: 1; position: relative; overflow: hidden; }
.kg-legend { position: absolute; left: 16px; bottom: 16px; background: rgba(30,31,54,.92); border: 1px solid #2d2f4a; border-radius: 10px; padding: 10px 12px; backdrop-filter: blur(8px); box-shadow: 0 2px 12px rgba(0,0,0,.25); z-index: 5; }
.kg-legend-title { font-size: 11px; font-weight: 700; color: #6b7094; margin-bottom: 7px; text-transform: uppercase; letter-spacing: .05em; }
.kg-legend-items { display: flex; flex-direction: column; gap: 5px; }
.kg-legend-item { display: flex; align-items: center; gap: 7px; }
.kg-legend-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; box-shadow: 0 0 6px currentColor; }
.kg-legend-label { font-size: 11px; color: #8b8fa3; }
.kg-legend-toggle { margin-top: 8px; width: 100%; padding: 4px 0; border: 1px solid #2d2f4a; border-radius: 6px; background: #232541; font-size: 11px; color: #6b7094; cursor: pointer; transition: all .15s; }
.kg-legend-toggle:hover { background: #2d2f4a; color: #c4c9e2; }
.kg-zoom { position: absolute; right: 16px; bottom: 16px; display: flex; flex-direction: column; align-items: center; gap: 2px; background: rgba(30,31,54,.92); border: 1px solid #2d2f4a; border-radius: 10px; padding: 6px; box-shadow: 0 2px 12px rgba(0,0,0,.25); z-index: 5; }
.kg-zbtn { width: 28px; height: 28px; border-radius: 6px; border: none; background: none; color: #6b7094; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s; }
.kg-zbtn:hover { background: #2d2f4a; color: #c4c9e2; }
.kg-zlevel { font-size: 10px; color: #6b7094; padding: 2px 0; }
.kg-stats { position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%); background: rgba(30,31,54,.9); border: 1px solid #2d2f4a; border-radius: 20px; padding: 4px 14px; font-size: 11px; color: #6b7094; box-shadow: 0 1px 6px rgba(0,0,0,.2); z-index: 5; }
.kg-stats-user { color: #a78bfa; }
.kg-link-hint { position: absolute; top: 16px; left: 50%; transform: translateX(-50%); background: rgba(99,102,241,.12); border: 1px solid rgba(99,102,241,.3); border-radius: 20px; padding: 6px 16px; font-size: 12px; color: #a78bfa; font-weight: 600; z-index: 5; box-shadow: 0 2px 8px rgba(99,102,241,.2); }
.kg-edge-actions { position: absolute; top: 16px; left: 50%; transform: translateX(-50%); display: flex; align-items: center; gap: 8px; background: rgba(30,31,54,.95); border: 1px solid #2d2f4a; border-radius: 10px; padding: 6px 12px; box-shadow: 0 2px 12px rgba(0,0,0,.25); z-index: 5; }
.kg-ea-label { font-size: 12px; font-weight: 600; color: #c4c9e2; }
.kg-ea-weight { font-size: 11px; color: #a78bfa; background: rgba(99,102,241,.12); padding: 2px 6px; border-radius: 8px; }
.kg-ea-btn { display: inline-flex; align-items: center; gap: 3px; padding: 4px 8px; border-radius: 6px; border: 1px solid #2d2f4a; background: #232541; font-size: 11px; color: #8b8fa3; cursor: pointer; transition: all .15s; }
.kg-ea-btn:hover { background: #2d2f4a; color: #c4c9e2; }
.kg-ea-btn--danger:hover { background: rgba(239,68,68,.15); color: #f87171; border-color: rgba(239,68,68,.3); }
.modal-enter-active, .modal-leave-active { transition: all .25s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-from .kg-container, .modal-leave-to .kg-container { opacity: 0; }
</style>
