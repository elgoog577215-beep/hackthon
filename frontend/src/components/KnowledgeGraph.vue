<template>
  <div class="knowledge-graph-container">
    <!-- Toolbar -->
    <div class="graph-toolbar">
      <div class="toolbar-left">
        <span class="graph-title">知识图谱</span>
        <span v-if="loading" class="loading-indicator">
          <el-icon class="is-loading"><Loading /></el-icon>
          生成中...
        </span>
      </div>
      <div class="toolbar-right">
        <button
          v-if="!hasGraph"
          class="btn-generate"
          :disabled="loading"
          @click="generateGraph"
        >
          <el-icon><MagicStick /></el-icon>
          生成图谱
        </button>
        <button
          v-else
          class="btn-refresh"
          :disabled="loading"
          @click="generateGraph"
        >
          <el-icon><Refresh /></el-icon>
          重新生成
        </button>
        <button class="btn-reset" @click="resetView">
          <el-icon><FullScreen /></el-icon>
          重置视图
        </button>
        <button class="btn-reset" @click="downloadImage" title="导出图片">
          <el-icon><Download /></el-icon>
          导出
        </button>
      </div>
    </div>

    <!-- Graph Canvas -->
    <div ref="graphContainer" class="graph-canvas" @click="deselectNode">
      <svg
        :viewBox="viewBoxString"
        class="graph-svg"
        @wheel.prevent="handleWheel"
        @mousedown="handleMouseDown"
        @mousemove="handleMouseMove"
        @mouseup="handleMouseUp"
        @mouseleave="handleMouseUp"
      >
        <defs>
          <!-- Background Grid -->
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#f1f5f9" stroke-width="1"/>
          </pattern>
          <!-- Drop Shadow Filter -->
          <filter id="node-shadow" x="-50%" y="-50%" width="200%" height="200%">
            <feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="#000000" flood-opacity="0.1"/>
          </filter>
          <!-- Selected Glow -->
          <filter id="node-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feDropShadow dx="0" dy="0" stdDeviation="6" flood-color="#6366f1" flood-opacity="0.5"/>
          </filter>
          <!-- Arrowhead Marker -->
          <marker
            id="arrowhead"
            viewBox="0 0 10 10"
            refX="28" 
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
          </marker>
        </defs>
        
        <rect width="100%" height="100%" fill="url(#grid)" />

        <!-- Edges -->
        <g class="edges">
          <path
            v-for="edge in graphData.edges"
            :key="`${edge.source}-${edge.target}`"
            :d="getEdgePath(edge)"
            :class="['edge-line', getEdgeClass(edge)]"
            :stroke-width="selectedNode && (edge.source === selectedNode.id || edge.target === selectedNode.id) ? 3 : 2"
            marker-end="url(#arrowhead)"
          />
        </g>

        <!-- Nodes -->
        <g class="nodes">
          <g
            v-for="node in graphData.nodes"
            :key="node.id"
            class="node-group"
            :transform="`translate(${getNodePosition(node.id).x}, ${getNodePosition(node.id).y})`"
            @click.stop="selectNode(node)"
            @mousedown.stop="handleNodeMouseDown($event, node)"
            @mouseenter="hoverNode = node.id"
            @mouseleave="hoverNode = null"
          >
            <!-- Invisible Hit Area (Larger than visual) -->
            <rect
              :x="-getNodeWidth(node) / 2 - 10"
              :y="-30"
              :width="getNodeWidth(node) + 20"
              height="60"
              fill="transparent"
            />

            <!-- Node Card Background -->
            <rect
              :x="-getNodeWidth(node) / 2"
              :y="-22"
              :width="getNodeWidth(node)"
              height="44"
              rx="6"
              ry="6"
              class="node-card-bg"
              :filter="selectedNode?.id === node.id ? 'url(#node-glow)' : 'url(#node-shadow)'"
              :stroke="selectedNode?.id === node.id ? '#6366f1' : 'transparent'"
              stroke-width="2"
            />
            
            <!-- Type Indicator Strip -->
            <rect
              :x="-getNodeWidth(node) / 2"
              :y="-22"
              width="5"
              height="44"
              rx="0"
              class="node-type-strip"
              :fill="getNodeColor(node)"
              style="border-top-left-radius: 6px; border-bottom-left-radius: 6px;"
            />

            <!-- Node Label -->
            <text
              class="node-label"
              x="5"
              y="6"
              text-anchor="middle"
              :style="{ fill: '#0f172a' }"
            >
              {{ node.label }}
            </text>
          </g>
        </g>
      </svg>

      <!-- Empty State -->
      <div v-if="!hasGraph && !loading" class="empty-state">
        <el-icon class="empty-icon"><MagicStick /></el-icon>
        <p class="empty-text">暂无知识图谱数据</p>
        <button class="btn-generate-large" @click="generateGraph">
          立即生成
        </button>
      </div>

      <!-- Node Detail Panel -->
      <transition name="slide">
        <div v-if="selectedNode" class="node-detail-panel">
          <div class="panel-header">
            <h3>{{ selectedNode.label }}</h3>
            <button class="btn-close" @click="deselectNode">
              <el-icon><Close /></el-icon>
            </button>
          </div>
          <div class="panel-content">
            <div class="info-row">
              <span class="info-label">类型:</span>
              <span class="info-value" :style="{ background: getNodeColor(selectedNode) + '20', color: getNodeColor(selectedNode) }">
                {{ getNodeTypeLabel(selectedNode.type) }}
              </span>
            </div>
            <div v-if="selectedNode.description" class="info-row">
              <span class="info-label">描述:</span>
              <p class="info-description">{{ selectedNode.description }}</p>
            </div>
            <div v-if="selectedNode.chapter_id" class="info-row">
              <button class="btn-navigate" @click="navigateToNode(selectedNode.chapter_id)">
                <el-icon><Position /></el-icon>
                前往学习
              </button>
            </div>
          </div>
        </div>
      </transition>
    </div>

    <!-- Legend -->
    <div class="graph-legend">
      <div class="legend-title">图例</div>
      <div class="legend-items">
        <div v-for="type in nodeTypes" :key="type.value" class="legend-item">
          <span class="legend-dot" :style="{ background: type.color }"></span>
          <span class="legend-label">{{ type.label }}</span>
        </div>
      </div>
    </div>

    <!-- Stats -->
    <div v-if="hasGraph" class="graph-stats">
      <span>{{ graphData.nodes.length }} 个节点</span>
      <span>{{ graphData.edges.length }} 条关系</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useCourseStore } from '../stores/course'
import { ElMessage } from 'element-plus'
import { Loading, MagicStick, Refresh, FullScreen, Close, Position } from '@element-plus/icons-vue'

const courseStore = useCourseStore()

// State
const loading = ref(false)
const graphData = ref<{ nodes: any[], edges: any[] }>({ nodes: [], edges: [] })
const selectedNode = ref<any>(null)
const hoverNode = ref<string | null>(null)
const graphContainer = ref<HTMLElement | null>(null)

// ViewBox for zooming and panning
const viewBox = ref({ x: -100, y: -300, width: 1000, height: 700 })
const viewBoxString = computed(() => `${viewBox.value.x} ${viewBox.value.y} ${viewBox.value.width} ${viewBox.value.height}`)

const isDragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })
const viewBoxStart = ref({ x: 0, y: 0 })

// Node Dragging State
const draggingNode = ref<any>(null)
const dragOffset = ref({ x: 0, y: 0 })

// Node type configuration
const nodeTypes = [
  { value: 'root', label: '课程核心', color: '#4f46e5' },    // Indigo-600
  { value: 'module', label: '知识模块', color: '#7c3aed' },  // Violet-600
  { value: 'concept', label: '核心概念', color: '#059669' }, // Emerald-600
  { value: 'theorem', label: '关键定理', color: '#d97706' }, // Amber-600
  { value: 'method', label: '核心方法', color: '#db2777' },  // Pink-600
  // Backward compatibility
  { value: 'core', label: '核心概念', color: '#4f46e5' },
  { value: 'basic', label: '基础概念', color: '#059669' },
  { value: 'advanced', label: '进阶概念', color: '#d97706' },
  { value: 'application', label: '应用场景', color: '#db2777' }
]

// Computed
const hasGraph = computed(() => graphData.value.nodes.length > 0)

// Initialize - load cached graph
onMounted(async () => {
  await loadGraph()
})

// Watch for course changes
watch(() => courseStore.currentCourseId, async () => {
  await loadGraph()
})

// Load graph from API
async function loadGraph() {
  if (!courseStore.currentCourseId) return
  
  try {
    const response = await fetch(`/courses/${courseStore.currentCourseId}/knowledge_graph`)
    const contentType = response.headers.get("content-type");
    if (response.ok && contentType && contentType.indexOf("application/json") !== -1) {
        const result = await response.json()
        
        if (result.status === 'success' && result.data.nodes.length > 0) {
          graphData.value = result.data
          calculateTreeLayout()
        }
    }
  } catch (error) {
    console.error('Failed to load knowledge graph:', error)
  }
}

// Generate graph using AI
async function generateGraph() {
  if (!courseStore.currentCourseId) {
    ElMessage.warning('请先选择课程')
    return
  }
  
  loading.value = true
  try {
    const response = await fetch(`/courses/${courseStore.currentCourseId}/knowledge_graph`, {
      method: 'POST'
    })
    
    const contentType = response.headers.get("content-type");
    if (response.ok && contentType && contentType.indexOf("application/json") !== -1) {
        const result = await response.json()
        
        if (result.status === 'success') {
          graphData.value = result.data
          calculateTreeLayout()
          ElMessage.success('知识图谱生成成功')
        } else {
          ElMessage.error('生成失败: ' + (result.message || 'Unknown error'))
        }
    } else {
        ElMessage.error('生成失败: 服务器返回错误')
    }
  } catch (error) {
    console.error('Failed to generate knowledge graph:', error instanceof Error ? error.message : error)
    ElMessage.error('生成失败')
  } finally {
    loading.value = false
  }
}

// ----------------------------------------------------------------------
// Tree Layout Algorithm (Left-to-Right)
// ----------------------------------------------------------------------
function calculateTreeLayout() {
  const nodes = graphData.value.nodes
  const edges = graphData.value.edges
  
  if (nodes.length === 0) return

  // 1. Build Adjacency List (Directed)
  const childrenMap: Record<string, string[]> = {}
  const parentMap: Record<string, string[]> = {}
  
  nodes.forEach(n => {
    childrenMap[n.id] = []
    parentMap[n.id] = []
  })
  
  edges.forEach(e => {
    if (childrenMap[e.source]) {
      childrenMap[e.source]!.push(e.target)
    }
    if (parentMap[e.target]) {
      parentMap[e.target]!.push(e.source)
    }
  })

  // 2. Identify Roots (Nodes with no incoming edges, or specific type)
  let roots = nodes.filter(n => (parentMap[n.id] || []).length === 0)
  
  // If circular or no clear root, fallback to 'root' type or just the first node
  if (roots.length === 0) {
    const explicitRoot = nodes.find(n => n.type === 'root')
    roots = explicitRoot ? [explicitRoot] : [nodes[0]]
  }

  // 3. DFS for layout
  const visited = new Set<string>()
  let currentY = 0
  const LEVEL_WIDTH = 280
  const NODE_HEIGHT = 70 // Height + Gap

  // Helper to get node object
  const getNode = (id: string) => nodes.find(n => n.id === id)

  // Recursive layout function
  // Returns the Y-center of the subtree rooted at `nodeId`
  function layoutNode(nodeId: string, depth: number): number {
    if (visited.has(nodeId)) {
      // If already visited, we treat it as a cross-link target, 
      // but we don't move it. It stays where it was first placed.
      // Or we could return its existing Y? 
      // For a simple tree layout, we just skip re-layouting.
      const node = getNode(nodeId)
      return node ? node.y : currentY
    }
    
    visited.add(nodeId)
    const node = getNode(nodeId)
    if (!node) return currentY

    // Position X
    node.x = depth * LEVEL_WIDTH

    // Process children
    const childrenIds = childrenMap[nodeId] || []
    // Filter out already visited children to strictly enforce tree structure for layout
    const unvisitedChildren = childrenIds.filter(id => !visited.has(id))

    if (unvisitedChildren.length === 0) {
      // Leaf node
      node.y = currentY
      currentY += NODE_HEIGHT
      return node.y
    } else {
      // Parent node: place children, then center self
      let firstChildY: number | null = null
      let lastChildY: number | null = null

      unvisitedChildren.forEach((childId, index) => {
        const childY = layoutNode(childId, depth + 1)
        if (index === 0) firstChildY = childY
        lastChildY = childY
      })

      if (firstChildY !== null && lastChildY !== null) {
        node.y = (firstChildY + lastChildY) / 2
      } else {
        node.y = currentY
        currentY += NODE_HEIGHT
      }
      return node.y
    }
  }

  // Layout each root (handles forests)
  roots.forEach(root => {
    layoutNode(root.id, 0)
  })

  // Handle any nodes not reached (disconnected components)
  nodes.forEach(node => {
    if (!visited.has(node.id)) {
      layoutNode(node.id, 0)
    }
  })
  
  updateViewBox()
}

// Update viewBox to fit all nodes with generous padding
function updateViewBox() {
  if (graphData.value.nodes.length === 0) return
  
  const paddingX = 300
  const paddingY = 200
  const xs = graphData.value.nodes.map(n => n.x)
  const ys = graphData.value.nodes.map(n => n.y)
  
  const minX = Math.min(...xs) - paddingX
  const maxX = Math.max(...xs) + paddingX
  const minY = Math.min(...ys) - paddingY
  const maxY = Math.max(...ys) + paddingY
  
  viewBox.value = {
    x: minX,
    y: minY,
    width: Math.max(maxX - minX, 800),
    height: Math.max(maxY - minY, 600)
  }
}

function getNodePosition(nodeId: string) {
  const node = graphData.value.nodes.find(n => n.id === nodeId)
  return node ? { x: node.x || 0, y: node.y || 0 } : { x: 0, y: 0 }
}

function getNodeWidth(node: any) {
  const len = node.label ? node.label.length : 0
  // slightly wider cards for better text breathing room
  return Math.max(120, len * 15 + 40)
}

function getNodeColor(node: any) {
  const typeInfo = nodeTypes.find(t => t.value === node.type)
  return typeInfo?.color || '#94a3b8'
}

function getEdgePath(edge: any) {
  const source = getNodePosition(edge.source)
  const target = getNodePosition(edge.target)
  
  // Bezier Curve (Cubic)
  // Control points: halfway horizontally
  const dx = target.x - source.x
  const cp1x = source.x + dx * 0.5
  const cp1y = source.y
  const cp2x = target.x - dx * 0.5
  const cp2y = target.y
  
  return `M ${source.x} ${source.y} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${target.x} ${target.y}`
}

function getEdgeClass(edge: any) {
  const classes = [edge.relation]
  if (selectedNode.value) {
    const isConnected = edge.source === selectedNode.value.id || 
                       edge.target === selectedNode.value.id
    if (isConnected) classes.push('highlighted')
    else classes.push('dimmed')
  }
  return classes.join(' ')
}

function getNodeTypeLabel(type: string) {
  const typeInfo = nodeTypes.find(t => t.value === type)
  return typeInfo?.label || type
}

function selectNode(node: any) {
  selectedNode.value = node
}

function deselectNode() {
  selectedNode.value = null
}

function navigateToNode(nodeId: string) {
  courseStore.scrollToNode(nodeId)
  ElMessage.success('已跳转到对应章节')
}

function resetView() {
  updateViewBox()
}


// Download Graph as Image
function downloadImage() {
  if (!graphContainer.value) return
  
  const svg = graphContainer.value.querySelector('svg')
  if (!svg) return

  // Serialize SVG
  const serializer = new XMLSerializer()
  let source = serializer.serializeToString(svg)

  // Add namespaces
  if(!source.match(/^<svg[^>]+xmlns="http\:\/\/www\.w3\.org\/2000\/svg"/)){
      source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"')
  }
  if(!source.match(/^<svg[^>]+xmlns:xlink="http\:\/\/www\.w3\.org\/1999\/xlink"/)){
      source = source.replace(/^<svg/, '<svg xmlns:xlink="http://www.w3.org/1999/xlink"')
  }

  // Create Blob
  const blob = new Blob([source], {type: "image/svg+xml;charset=utf-8"})
  const url = URL.createObjectURL(blob)
  
  // Create link and download
  const link = document.createElement('a')
  link.href = url
  link.download = `knowledge-graph-${courseStore.currentCourseId}.svg`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  
  ElMessage.success('已导出 SVG 图片')
}

// Zoom handling
function handleWheel(e: WheelEvent) {
  const scale = e.deltaY > 0 ? 1.1 : 0.9
  const centerX = viewBox.value.x + viewBox.value.width / 2
  const centerY = viewBox.value.y + viewBox.value.height / 2
  
  viewBox.value.width *= scale
  viewBox.value.height *= scale
  viewBox.value.x = centerX - viewBox.value.width / 2
  viewBox.value.y = centerY - viewBox.value.height / 2
}

// Helper to convert screen coordinates to SVG coordinates
function getSvgPoint(clientX: number, clientY: number) {
  if (!graphContainer.value) return { x: 0, y: 0 }
  const rect = graphContainer.value.getBoundingClientRect()
  const x = viewBox.value.x + (clientX - rect.left) * (viewBox.value.width / rect.width)
  const y = viewBox.value.y + (clientY - rect.top) * (viewBox.value.height / rect.height)
  return { x, y }
}

function handleNodeMouseDown(e: MouseEvent, node: any) {
  // Prevent canvas panning
  draggingNode.value = node
  const mousePos = getSvgPoint(e.clientX, e.clientY)
  dragOffset.value = {
    x: node.x - mousePos.x,
    y: node.y - mousePos.y
  }
}

// Pan handling
function handleMouseDown(e: MouseEvent) {
  if (draggingNode.value) return
  isDragging.value = true
  dragStart.value = { x: e.clientX, y: e.clientY }
  viewBoxStart.value = { x: viewBox.value.x, y: viewBox.value.y }
}

let animationFrameId: number | null = null

function handleMouseMove(e: MouseEvent) {
  if (animationFrameId) return

  animationFrameId = requestAnimationFrame(() => {
    animationFrameId = null
    
    if (draggingNode.value) {
      const mousePos = getSvgPoint(e.clientX, e.clientY)
      draggingNode.value.x = mousePos.x + dragOffset.value.x
      draggingNode.value.y = mousePos.y + dragOffset.value.y
      return
    }

    if (!isDragging.value) return
    
    const dx = (e.clientX - dragStart.value.x) * viewBox.value.width / (graphContainer.value?.clientWidth || 800)
    const dy = (e.clientY - dragStart.value.y) * viewBox.value.height / (graphContainer.value?.clientHeight || 600)
    
    viewBox.value.x = viewBoxStart.value.x - dx
    viewBox.value.y = viewBoxStart.value.y - dy
  })
}

function handleMouseUp() {
  isDragging.value = false
  draggingNode.value = null
}
</script>

<style scoped>
.knowledge-graph-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f8fafc;
  border-radius: 12px;
  overflow: hidden;
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
}

.graph-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid #f1f5f9;
  z-index: 10;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.graph-title {
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: -0.5px;
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #6366f1;
  background: #e0e7ff;
  padding: 4px 10px;
  border-radius: 20px;
}

.toolbar-right {
  display: flex;
  gap: 10px;
}

.btn-generate,
.btn-refresh,
.btn-reset {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  border: none;
}

.btn-generate {
  background: #1e293b;
  color: white;
  box-shadow: 0 4px 12px rgba(30, 41, 59, 0.2);
}

.btn-generate:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(30, 41, 59, 0.3);
}

.btn-refresh {
  background: white;
  color: #475569;
  border: 1px solid #e2e8f0;
}

.btn-refresh:hover:not(:disabled) {
  border-color: #cbd5e1;
  background: #f8fafc;
}

.btn-reset {
  background: transparent;
  color: #64748b;
}

.btn-reset:hover {
  background: #f1f5f9;
  color: #334155;
}

.graph-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
  cursor: grab;
  background: #f8fafc;
}

.graph-canvas:active {
  cursor: grabbing;
}

.graph-svg {
  width: 100%;
  height: 100%;
}

/* Edges */
.edge-line {
  stroke: #64748b;
  fill: none;
  transition: stroke 0.3s ease, opacity 0.3s ease;
}

.edge-line.highlighted {
  stroke: #6366f1;
  stroke-width: 3px;
  filter: drop-shadow(0 0 4px rgba(99, 102, 241, 0.3));
}

.edge-line.dimmed {
  stroke: #cbd5e1;
  opacity: 0.3;
}

/* Nodes */
.node-group {
  cursor: pointer;
  /* Removed transform transition to fix jitter */
  transition: filter 0.2s ease;
}

/* Hover effect only changes filter/color, not position/scale */
.node-group:hover .node-card-bg {
  stroke: #6366f1;
  filter: url(#node-glow);
}

.node-card-bg {
  fill: white;
  transition: all 0.2s ease;
}

.node-label {
  font-size: 14px;
  font-weight: 700;
  font-family: 'Inter', sans-serif;
  letter-spacing: 0.3px;
  pointer-events: none;
  user-select: none;
}

/* Node Detail Panel */
.node-detail-panel {
  position: absolute;
  top: 24px;
  right: 24px;
  width: 320px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(16px);
  border-radius: 16px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.5);
  overflow: hidden;
  z-index: 20;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #f1f5f9;
}

.panel-header h3 {
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
}

.btn-close {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: #f1f5f9;
  color: #64748b;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.btn-close:hover {
  background: #e2e8f0;
  color: #334155;
}

.panel-content {
  padding: 24px;
}

.info-row {
  margin-bottom: 16px;
}

.info-label {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  display: block;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.info-value {
  display: inline-block;
  font-size: 13px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 8px;
}

.info-description {
  font-size: 14px;
  color: #475569;
  line-height: 1.6;
  margin: 0;
  background: #f8fafc;
  padding: 12px;
  border-radius: 8px;
}

.btn-navigate {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 12px;
  background: #1e293b;
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  margin-top: 8px;
}

.btn-navigate:hover {
  background: #0f172a;
  transform: translateY(-1px);
}

/* Legend */
.graph-legend {
  position: absolute;
  bottom: 24px;
  left: 24px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.5);
}

.legend-title {
  font-size: 12px;
  font-weight: 700;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}

.legend-items {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}

.legend-label {
  font-size: 13px;
  color: #475569;
  font-weight: 500;
}

/* Stats */
.graph-stats {
  position: absolute;
  bottom: 24px;
  right: 24px;
  display: flex;
  gap: 16px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
  padding: 10px 16px;
  border-radius: 24px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  border: 1px solid rgba(255, 255, 255, 0.5);
}

/* Transitions */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateX(20px) scale(0.95);
}

/* Empty State */
.empty-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  z-index: 10;
}

.empty-icon {
  font-size: 64px;
  color: #e2e8f0;
}

.empty-text {
  font-size: 16px;
  font-weight: 500;
  color: #94a3b8;
  margin: 0;
}

.btn-generate-large {
  padding: 14px 32px;
  background: #1e293b;
  color: white;
  border: none;
  border-radius: 16px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 10px 20px rgba(30, 41, 59, 0.2);
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.btn-generate-large:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 24px rgba(30, 41, 59, 0.3);
}
</style>
