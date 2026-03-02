<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="courseStore.showKnowledgeGraph" class="kg-overlay" @click.self="handleClose">
        <div class="kg-container">
          <!-- Header -->
          <div class="kg-header">
            <div class="kg-header-left">
              <button class="kg-btn-close" @click="handleClose">
                <el-icon><ArrowLeft /></el-icon>
              </button>
              <h2 class="kg-title">知识图谱</h2>
              <span v-if="loading" class="kg-loading">
                <el-icon class="is-loading"><Loading /></el-icon>
                生成中...
              </span>
            </div>
            
            <div class="kg-header-center" v-if="hasGraph">
              <div class="kg-search">
                <el-icon class="kg-search-icon"><Search /></el-icon>
                <input
                  v-model="searchQuery"
                  type="text"
                  placeholder="搜索节点..."
                  class="kg-search-input"
                  @keyup.enter="handleSearch"
                />
                <button v-if="searchQuery" class="kg-search-clear" @click="clearSearch">
                  <el-icon><CircleClose /></el-icon>
                </button>
              </div>
            </div>
            
            <div class="kg-header-right">
              <button v-if="!hasGraph" class="kg-btn kg-btn-primary" :disabled="loading" @click="generateGraph">
                <el-icon><MagicStick /></el-icon>
                生成图谱
              </button>
              <button v-else class="kg-btn kg-btn-secondary" :disabled="loading" @click="generateGraph">
                <el-icon><Refresh /></el-icon>
                重新生成
              </button>
              <button class="kg-btn kg-btn-ghost" @click="resetView" title="重置视图">
                <el-icon><FullScreen /></el-icon>
              </button>
              <button class="kg-btn kg-btn-ghost" @click="downloadImage" title="导出SVG">
                <el-icon><Download /></el-icon>
              </button>
            </div>
          </div>

          <!-- Graph Canvas -->
          <div ref="canvasRef" class="kg-canvas" @click="deselectNode">
            <!-- SVG Graph -->
            <svg
              v-if="hasGraph"
              :viewBox="viewBoxStr"
              class="kg-svg"
              @wheel.prevent="handleWheel"
              @mousedown="startPan"
              @mousemove="onPan"
              @mouseup="endPan"
              @mouseleave="endPan"
            >
              <defs>
                <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#e2e8f0" stroke-width="1"/>
                </pattern>
                <filter id="shadow" x="-50%" y="-50%" width="200%" height="200%">
                  <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000" flood-opacity="0.1"/>
                </filter>
                <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                  <feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#6366f1" flood-opacity="0.4"/>
                </filter>
                <marker id="arrow" viewBox="0 0 10 10" refX="25" refY="5" markerWidth="5" markerHeight="5" orient="auto">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8"/>
                </marker>
              </defs>
              
              <rect width="100%" height="100%" fill="url(#grid)"/>
              
              <!-- Edges -->
              <g class="kg-edges">
                <path
                  v-for="edge in graphData.edges"
                  :key="edge.source + '-' + edge.target"
                  :d="getEdgePath(edge)"
                  class="kg-edge"
                  :class="getEdgeClass(edge)"
                  marker-end="url(#arrow)"
                />
              </g>
              
              <!-- Nodes -->
              <g class="kg-nodes">
                <g
                  v-for="node in graphData.nodes"
                  :key="node.id"
                  class="kg-node"
                  :class="{ 'kg-node-selected': selectedNode?.id === node.id }"
                  :transform="`translate(${node.x}, ${node.y})`"
                  @click.stop="selectNode(node)"
                  @mouseenter="hoveredNode = node.id"
                  @mouseleave="hoveredNode = null"
                >
                  <rect
                    :x="-getNodeWidth(node) / 2"
                    y="-20"
                    :width="getNodeWidth(node)"
                    height="40"
                    rx="8"
                    class="kg-node-bg"
                    :style="{ fill: getNodeColor(node) + '15', stroke: getNodeColor(node) }"
                  />
                  <rect
                    :x="-getNodeWidth(node) / 2"
                    y="-20"
                    width="4"
                    height="40"
                    rx="2"
                    :fill="getNodeColor(node)"
                  />
                  <text
                    :x="4"
                    y="6"
                    class="kg-node-label"
                  >{{ node.label }}</text>
                </g>
              </g>
            </svg>

            <!-- Empty State -->
            <div v-if="!hasGraph && !loading" class="kg-empty">
              <el-icon class="kg-empty-icon"><Connection /></el-icon>
              <p class="kg-empty-text">暂无知识图谱</p>
              <button class="kg-btn kg-btn-primary kg-btn-large" @click="generateGraph">
                <el-icon><MagicStick /></el-icon>
                立即生成
              </button>
            </div>

            <!-- Node Detail Panel -->
            <Transition name="slide">
              <div v-if="selectedNode" class="kg-detail">
                <div class="kg-detail-header">
                  <h3>{{ selectedNode.label }}</h3>
                  <button class="kg-btn-close-sm" @click="deselectNode">
                    <el-icon><Close /></el-icon>
                  </button>
                </div>
                <div class="kg-detail-body">
                  <div class="kg-detail-row">
                    <span class="kg-detail-label">类型</span>
                    <span 
                      class="kg-detail-value" 
                      :style="{ background: getNodeColor(selectedNode) + '20', color: getNodeColor(selectedNode) }"
                    >{{ getTypeLabel(selectedNode.type) }}</span>
                  </div>
                  <div v-if="selectedNode.description" class="kg-detail-row">
                    <span class="kg-detail-label">描述</span>
                    <p class="kg-detail-desc">{{ selectedNode.description }}</p>
                  </div>
                  <button 
                    v-if="selectedNode.chapter_id" 
                    class="kg-btn kg-btn-primary kg-btn-block"
                    @click="navigateToNode(selectedNode.chapter_id)"
                  >
                    <el-icon><Position /></el-icon>
                    前往学习
                  </button>
                </div>
              </div>
            </Transition>
          </div>

          <!-- Legend -->
          <div v-if="hasGraph" class="kg-legend">
            <div class="kg-legend-title">图例</div>
            <div class="kg-legend-items">
              <div v-for="type in nodeTypes" :key="type.value" class="kg-legend-item">
                <span class="kg-legend-dot" :style="{ background: type.color }"></span>
                <span class="kg-legend-label">{{ type.label }}</span>
              </div>
            </div>
          </div>

          <!-- Zoom Controls -->
          <div v-if="hasGraph" class="kg-zoom">
            <button class="kg-zoom-btn" @click="zoomIn">
              <el-icon><ZoomIn /></el-icon>
            </button>
            <span class="kg-zoom-level">{{ zoomLevel }}%</span>
            <button class="kg-zoom-btn" @click="zoomOut">
              <el-icon><ZoomOut /></el-icon>
            </button>
          </div>

          <!-- Stats -->
          <div v-if="hasGraph" class="kg-stats">
            <span>{{ graphData.nodes.length }} 个节点</span>
            <span>{{ graphData.edges.length }} 条关系</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useCourseStore } from '../stores/course'
import { ElMessage } from 'element-plus'
import { 
  ArrowLeft, Loading, MagicStick, Refresh, FullScreen, Download,
  Search, CircleClose, Connection, Close, Position, ZoomIn, ZoomOut
} from '@element-plus/icons-vue'

const courseStore = useCourseStore()

// State
const loading = ref(false)
const graphData = ref<{ nodes: any[], edges: any[] }>({ nodes: [], edges: [] })
const selectedNode = ref<any>(null)
const hoveredNode = ref<string | null>(null)
const searchQuery = ref('')
const canvasRef = ref<HTMLElement | null>(null)

// ViewBox
const viewBox = ref({ x: 0, y: 0, width: 1000, height: 700 })
const viewBoxStr = computed(() => `${viewBox.value.x} ${viewBox.value.y} ${viewBox.value.width} ${viewBox.value.height}`)
const zoomLevel = computed(() => Math.round(1000 / viewBox.value.width * 100))

// Panning
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0 })
const viewBoxStart = ref({ x: 0, y: 0 })

// Node types
const nodeTypes = [
  { value: 'root', label: '核心主题', color: '#4f46e5' },
  { value: 'module', label: '知识模块', color: '#7c3aed' },
  { value: 'concept', label: '核心概念', color: '#059669' },
  { value: 'theorem', label: '关键定理', color: '#d97706' },
  { value: 'method', label: '核心方法', color: '#db2777' },
  { value: 'core', label: '核心概念', color: '#4f46e5' },
  { value: 'basic', label: '基础概念', color: '#059669' },
  { value: 'advanced', label: '进阶概念', color: '#d97706' },
  { value: 'application', label: '应用场景', color: '#db2777' }
]

const hasGraph = computed(() => graphData.value.nodes.length > 0)

// Close
const handleClose = () => {
  courseStore.showKnowledgeGraph = false
}

// Load graph
const loadGraph = async () => {
  if (!courseStore.currentCourseId) return
  
  try {
    const res = await fetch(`/courses/${courseStore.currentCourseId}/knowledge_graph`)
    const data = await res.json()
    
    if (data.status === 'success' && data.data.nodes?.length > 0) {
      graphData.value = data.data
      layoutGraph()
    }
  } catch (e) {
    console.error('Failed to load graph:', e)
  }
}

// Generate graph
const generateGraph = async () => {
  if (!courseStore.currentCourseId) {
    ElMessage.warning('请先选择课程')
    return
  }
  
  loading.value = true
  try {
    const res = await fetch(`/courses/${courseStore.currentCourseId}/knowledge_graph`, { method: 'POST' })
    const data = await res.json()
    
    if (data.status === 'success') {
      graphData.value = data.data
      layoutGraph()
      ElMessage.success('知识图谱生成成功')
    } else {
      ElMessage.error('生成失败: ' + (data.message || '未知错误'))
    }
  } catch (e) {
    console.error('Failed to generate graph:', e)
    ElMessage.error('生成失败')
  } finally {
    loading.value = false
  }
}

// Layout algorithm
const layoutGraph = () => {
  const nodes = graphData.value.nodes
  const edges = graphData.value.edges
  if (!nodes.length) return

  // Build adjacency
  const children: Record<string, string[]> = {}
  const parents: Record<string, string[]> = {}
  nodes.forEach(n => { children[n.id] = []; parents[n.id] = [] })
  edges.forEach(e => {
    const childList = children[e.source]
    const parentList = parents[e.target]
    if (childList) childList.push(e.target)
    if (parentList) parentList.push(e.source)
  })

  // Find roots
  let roots = nodes.filter(n => !parents[n.id]?.length)
  if (!roots.length) roots = [nodes.find(n => n.type === 'root') || nodes[0]]

  // DFS layout
  const visited = new Set<string>()
  let currentY = 0
  const LEVEL_WIDTH = 250
  const NODE_HEIGHT = 60

  const layout = (nodeId: string, depth: number): number => {
    if (visited.has(nodeId)) {
      const node = nodes.find(n => n.id === nodeId)
      return node?.y ?? currentY
    }
    
    visited.add(nodeId)
    const node = nodes.find(n => n.id === nodeId)
    if (!node) return currentY

    node.x = depth * LEVEL_WIDTH
    
    const childIds = (children[nodeId] || []).filter(id => !visited.has(id))
    
    if (!childIds.length) {
      node.y = currentY
      currentY += NODE_HEIGHT
      return node.y
    }

    let firstY: number | null = null
    let lastY: number | null = null
    
    childIds.forEach((childId, i) => {
      const childY = layout(childId, depth + 1)
      if (i === 0) firstY = childY
      lastY = childY
    })

    node.y = firstY !== null && lastY !== null ? (firstY + lastY) / 2 : currentY
    return node.y
  }

  roots.forEach(root => layout(root.id, 0))
  nodes.forEach(node => {
    if (!visited.has(node.id)) layout(node.id, 0)
  })

  fitView()
}

// Fit view to nodes
const fitView = () => {
  const nodes = graphData.value.nodes
  if (!nodes.length) return

  const padding = 150
  const xs = nodes.map(n => n.x)
  const ys = nodes.map(n => n.y)
  
  const minX = Math.min(...xs) - padding
  const maxX = Math.max(...xs) + padding
  const minY = Math.min(...ys) - padding
  const maxY = Math.max(...ys) + padding

  viewBox.value = {
    x: minX,
    y: minY,
    width: Math.max(maxX - minX, 800),
    height: Math.max(maxY - minY, 600)
  }
}

// Node helpers
const getNodeWidth = (node: any) => Math.max(100, (node.label?.length || 0) * 14 + 30)
const getNodeColor = (node: any) => nodeTypes.find(t => t.value === node.type)?.color || '#94a3b8'
const getTypeLabel = (type: string) => nodeTypes.find(t => t.value === type)?.label || type

// Edge path
const getEdgePath = (edge: any) => {
  const source = graphData.value.nodes.find(n => n.id === edge.source)
  const target = graphData.value.nodes.find(n => n.id === edge.target)
  if (!source || !target) return ''
  
  const dx = target.x - source.x
  const cp1x = source.x + dx * 0.5
  const cp2x = target.x - dx * 0.5
  
  return `M ${source.x} ${source.y} C ${cp1x} ${source.y}, ${cp2x} ${target.y}, ${target.x} ${target.y}`
}

const getEdgeClass = (edge: any) => {
  if (!selectedNode.value) return ''
  const isConnected = edge.source === selectedNode.value.id || edge.target === selectedNode.value.id
  return isConnected ? 'kg-edge-highlight' : 'kg-edge-dim'
}

// Selection
const selectNode = (node: any) => { selectedNode.value = node }
const deselectNode = () => { selectedNode.value = null }

// Navigation
const navigateToNode = (nodeId: string) => {
  courseStore.scrollToNode(nodeId)
  handleClose()
  ElMessage.success('已跳转到对应章节')
}

// Search
const handleSearch = () => {
  if (!searchQuery.value.trim()) return
  
  const query = searchQuery.value.toLowerCase()
  const found = graphData.value.nodes.find(n => 
    n.label?.toLowerCase().includes(query) ||
    n.description?.toLowerCase().includes(query)
  )
  
  if (found) {
    selectNode(found)
    viewBox.value = {
      x: found.x - 150,
      y: found.y - 100,
      width: 300,
      height: 200
    }
  } else {
    ElMessage.info('未找到匹配的节点')
  }
}

const clearSearch = () => {
  searchQuery.value = ''
}

// Zoom
const zoomIn = () => {
  const cx = viewBox.value.x + viewBox.value.width / 2
  const cy = viewBox.value.y + viewBox.value.height / 2
  viewBox.value.width *= 0.8
  viewBox.value.height *= 0.8
  viewBox.value.x = cx - viewBox.value.width / 2
  viewBox.value.y = cy - viewBox.value.height / 2
}

const zoomOut = () => {
  const cx = viewBox.value.x + viewBox.value.width / 2
  const cy = viewBox.value.y + viewBox.value.height / 2
  viewBox.value.width *= 1.25
  viewBox.value.height *= 1.25
  viewBox.value.x = cx - viewBox.value.width / 2
  viewBox.value.y = cy - viewBox.value.height / 2
}

const resetView = () => fitView()

// Wheel zoom
const handleWheel = (e: WheelEvent) => {
  const scale = e.deltaY > 0 ? 1.1 : 0.9
  const cx = viewBox.value.x + viewBox.value.width / 2
  const cy = viewBox.value.y + viewBox.value.height / 2
  viewBox.value.width *= scale
  viewBox.value.height *= scale
  viewBox.value.x = cx - viewBox.value.width / 2
  viewBox.value.y = cy - viewBox.value.height / 2
}

// Pan
const startPan = (e: MouseEvent) => {
  isPanning.value = true
  panStart.value = { x: e.clientX, y: e.clientY }
  viewBoxStart.value = { x: viewBox.value.x, y: viewBox.value.y }
}

const onPan = (e: MouseEvent) => {
  if (!isPanning.value || !canvasRef.value) return
  
  const rect = canvasRef.value.getBoundingClientRect()
  const dx = (e.clientX - panStart.value.x) * viewBox.value.width / rect.width
  const dy = (e.clientY - panStart.value.y) * viewBox.value.height / rect.height
  
  viewBox.value.x = viewBoxStart.value.x - dx
  viewBox.value.y = viewBoxStart.value.y - dy
}

const endPan = () => { isPanning.value = false }

// Download
const downloadImage = () => {
  if (!canvasRef.value) return
  
  const svg = canvasRef.value.querySelector('svg')
  if (!svg) return

  const serializer = new XMLSerializer()
  let source = serializer.serializeToString(svg)
  
  if (!source.includes('xmlns="http://www.w3.org/2000/svg"')) {
    source = source.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"')
  }

  const blob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  
  const link = document.createElement('a')
  link.href = url
  link.download = `knowledge-graph-${courseStore.currentCourseId}.svg`
  link.click()
  URL.revokeObjectURL(url)
  
  ElMessage.success('已导出 SVG')
}

// Watch
watch(() => courseStore.showKnowledgeGraph, (show) => {
  if (show) loadGraph()
})

watch(() => courseStore.currentCourseId, () => {
  if (courseStore.showKnowledgeGraph) loadGraph()
})
</script>

<style scoped>
.kg-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(16px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.kg-container {
  width: 100%;
  height: 100%;
  max-width: 1600px;
  max-height: 1000px;
  background: #f8fafc;
  border-radius: 20px;
  box-shadow: 0 25px 80px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.kg-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: white;
  border-bottom: 1px solid #e2e8f0;
  gap: 16px;
}

.kg-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.kg-btn-close {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: none;
  background: #f1f5f9;
  color: #64748b;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.kg-btn-close:hover {
  background: #e2e8f0;
  color: #334155;
}

.kg-title {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
}

.kg-loading {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #6366f1;
  background: #eef2ff;
  padding: 6px 12px;
  border-radius: 20px;
}

.kg-header-center {
  flex: 1;
  max-width: 400px;
}

.kg-search {
  position: relative;
  display: flex;
  align-items: center;
}

.kg-search-icon {
  position: absolute;
  left: 12px;
  color: #94a3b8;
}

.kg-search-input {
  width: 100%;
  padding: 10px 36px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  font-size: 14px;
  background: #f8fafc;
  transition: all 0.2s;
}

.kg-search-input:focus {
  outline: none;
  border-color: #6366f1;
  background: white;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.kg-search-clear {
  position: absolute;
  right: 8px;
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  display: flex;
}

.kg-search-clear:hover {
  color: #64748b;
}

.kg-header-right {
  display: flex;
  gap: 8px;
}

.kg-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.kg-btn-primary {
  background: #1e293b;
  color: white;
}

.kg-btn-primary:hover:not(:disabled) {
  background: #0f172a;
  transform: translateY(-1px);
}

.kg-btn-secondary {
  background: white;
  color: #475569;
  border: 1px solid #e2e8f0;
}

.kg-btn-secondary:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #cbd5e1;
}

.kg-btn-ghost {
  background: transparent;
  color: #64748b;
}

.kg-btn-ghost:hover {
  background: #f1f5f9;
  color: #334155;
}

.kg-btn-large {
  padding: 14px 28px;
  font-size: 15px;
  border-radius: 14px;
}

.kg-btn-block {
  width: 100%;
  justify-content: center;
}

.kg-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.kg-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
  cursor: grab;
}

.kg-canvas:active {
  cursor: grabbing;
}

.kg-svg {
  width: 100%;
  height: 100%;
}

.kg-edge {
  fill: none;
  stroke: #cbd5e1;
  stroke-width: 1.5;
  transition: all 0.3s;
}

.kg-edge-highlight {
  stroke: #6366f1;
  stroke-width: 2.5;
}

.kg-edge-dim {
  stroke: #e2e8f0;
  opacity: 0.4;
}

.kg-node {
  cursor: pointer;
  transition: filter 0.2s;
}

.kg-node:hover .kg-node-bg {
  filter: url(#glow);
}

.kg-node-selected .kg-node-bg {
  stroke-width: 2;
  filter: url(#glow);
}

.kg-node-bg {
  stroke-width: 1.5;
  transition: all 0.2s;
}

.kg-node-label {
  font-size: 13px;
  font-weight: 600;
  fill: #1e293b;
  font-family: system-ui, -apple-system, sans-serif;
  pointer-events: none;
  dominant-baseline: middle;
}

.kg-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
}

.kg-empty-icon {
  font-size: 72px;
  color: #e2e8f0;
}

.kg-empty-text {
  font-size: 16px;
  color: #94a3b8;
  margin: 0;
}

.kg-detail {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 320px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.12);
  overflow: hidden;
  z-index: 10;
}

.kg-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #f1f5f9;
}

.kg-detail-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
}

.kg-btn-close-sm {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: none;
  background: #f1f5f9;
  color: #64748b;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.kg-btn-close-sm:hover {
  background: #e2e8f0;
}

.kg-detail-body {
  padding: 20px;
}

.kg-detail-row {
  margin-bottom: 16px;
}

.kg-detail-row:last-child {
  margin-bottom: 0;
}

.kg-detail-label {
  display: block;
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.kg-detail-value {
  display: inline-block;
  font-size: 13px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 8px;
}

.kg-detail-desc {
  font-size: 14px;
  color: #475569;
  line-height: 1.6;
  margin: 0;
  background: #f8fafc;
  padding: 12px;
  border-radius: 10px;
}

.kg-legend {
  position: absolute;
  bottom: 20px;
  left: 20px;
  background: white;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
}

.kg-legend-title {
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}

.kg-legend-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kg-legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kg-legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
}

.kg-legend-label {
  font-size: 13px;
  color: #475569;
}

.kg-zoom {
  position: absolute;
  bottom: 20px;
  right: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  background: white;
  padding: 8px;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
}

.kg-zoom-btn {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.kg-zoom-btn:hover {
  background: #f1f5f9;
  color: #334155;
}

.kg-zoom-level {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
}

.kg-stats {
  position: absolute;
  bottom: 20px;
  right: 80px;
  display: flex;
  gap: 16px;
  background: white;
  padding: 10px 16px;
  border-radius: 20px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>
