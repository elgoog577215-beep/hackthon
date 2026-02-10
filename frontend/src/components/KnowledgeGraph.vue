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
        <!-- Background Grid -->
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#f1f5f9" stroke-width="1"/>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />

        <!-- Edges -->
        <g class="edges">
          <line
            v-for="edge in graphData.edges"
            :key="`${edge.source}-${edge.target}`"
            :x1="getNodePosition(edge.source).x"
            :y1="getNodePosition(edge.source).y"
            :x2="getNodePosition(edge.target).x"
            :y2="getNodePosition(edge.target).y"
            :class="['edge-line', getEdgeClass(edge)]"
            :stroke-width="selectedNode && (edge.source === selectedNode.id || edge.target === selectedNode.id) ? 3 : 1.5"
          />
          <!-- Edge Labels -->
          <g
            v-for="edge in graphData.edges"
            :key="`label-${edge.source}-${edge.target}`"
            class="edge-label"
            :transform="`translate(${getEdgeMidpoint(edge).x}, ${getEdgeMidpoint(edge).y})`"
          >
            <rect
              x="-20"
              y="-10"
              width="40"
              height="20"
              rx="4"
              fill="white"
              fill-opacity="0.9"
            />
            <text
              text-anchor="middle"
              dominant-baseline="middle"
              class="edge-label-text"
            >
              {{ edge.label }}
            </text>
          </g>
        </g>

        <!-- Nodes -->
        <g class="nodes">
          <g
            v-for="node in graphData.nodes"
            :key="node.id"
            class="node-group"
            :transform="`translate(${getNodePosition(node.id).x}, ${getNodePosition(node.id).y})`"
            @click.stop="selectNode(node)"
            @mouseenter="hoverNode = node.id"
            @mouseleave="hoverNode = null"
          >
            <!-- Node Circle -->
            <circle
              :r="getNodeRadius(node)"
              :class="['node-circle', getNodeClass(node)]"
              :stroke-width="selectedNode?.id === node.id ? 4 : 2"
            />
            <!-- Node Icon -->
            <text
              class="node-icon"
              dy="0.35em"
              text-anchor="middle"
            >
              {{ getNodeIcon(node) }}
            </text>
            <!-- Node Label -->
            <text
              class="node-label"
              :y="getNodeRadius(node) + 15"
              text-anchor="middle"
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
              <span class="info-value" :class="`type-${selectedNode.type}`">
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
          <span class="legend-dot" :class="`type-${type.value}`"></span>
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
const viewBox = ref({ x: -400, y: -300, width: 800, height: 600 })
const viewBoxString = computed(() => `${viewBox.value.x} ${viewBox.value.y} ${viewBox.value.width} ${viewBox.value.height}`)

const isDragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })
const viewBoxStart = ref({ x: 0, y: 0 })

// Node type configuration
const nodeTypes = [
  { value: 'root', label: '课程核心', color: '#6366f1' },
  { value: 'module', label: '知识模块', color: '#8b5cf6' },
  { value: 'concept', label: '核心概念', color: '#10b981' },
  { value: 'theorem', label: '关键定理', color: '#f59e0b' },
  { value: 'method', label: '核心方法', color: '#ec4899' },
  // Backward compatibility
  { value: 'core', label: '核心概念', color: '#6366f1' },
  { value: 'basic', label: '基础概念', color: '#10b981' },
  { value: 'advanced', label: '进阶概念', color: '#f59e0b' },
  { value: 'application', label: '应用场景', color: '#ec4899' }
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
    // Check if response is ok and is JSON
    const contentType = response.headers.get("content-type");
    if (response.ok && contentType && contentType.indexOf("application/json") !== -1) {
        const result = await response.json()
        
        if (result.status === 'success' && result.data.nodes.length > 0) {
          graphData.value = result.data
          // Calculate initial layout
          calculateLayout()
        }
    } else {
        // Handle non-JSON response (likely HTML error page)
        console.warn('Received non-JSON response for knowledge graph');
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
    
    // Check if response is ok and is JSON
    const contentType = response.headers.get("content-type");
    if (response.ok && contentType && contentType.indexOf("application/json") !== -1) {
        const result = await response.json()
        
        if (result.status === 'success') {
          graphData.value = result.data
          calculateLayout()
          ElMessage.success('知识图谱生成成功')
        } else {
          ElMessage.error('生成失败: ' + (result.message || 'Unknown error'))
        }
    } else {
        const text = await response.text();
        console.error('Server returned non-JSON response:', text.substring(0, 100));
        ElMessage.error('生成失败: 服务器返回错误')
    }
  } catch (error) {
    console.error('Failed to generate knowledge graph:', error instanceof Error ? error.message : error)
    ElMessage.error('生成失败')
  } finally {
    loading.value = false
  }
}

// Calculate force-directed layout
function calculateLayout() {
  const nodes = graphData.value.nodes
  const edges = graphData.value.edges
  
  // Initialize positions randomly
  nodes.forEach((node, i) => {
    if (!node.x || !node.y) {
      const angle = (i / nodes.length) * 2 * Math.PI
      const radius = 150 + Math.random() * 50
      node.x = Math.cos(angle) * radius
      node.y = Math.sin(angle) * radius
    }
  })
  
  // Simple force simulation (few iterations)
  for (let iteration = 0; iteration < 150; iteration++) {
    // Repulsion between nodes
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[j].x - nodes[i].x
        const dy = nodes[j].y - nodes[i].y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const force = 8000 / (dist * dist)
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        
        nodes[i].x -= fx
        nodes[i].y -= fy
        nodes[j].x += fx
        nodes[j].y += fy
      }
    }
    
    // Attraction along edges
    edges.forEach(edge => {
      const source = nodes.find(n => n.id === edge.source)
      const target = nodes.find(n => n.id === edge.target)
      if (source && target) {
        const dx = target.x - source.x
        const dy = target.y - source.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const force = (dist - 150) * 0.02
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        
        source.x += fx
        source.y += fy
        target.x -= fx
        target.y -= fy
      }
    })
    
    // Center gravity (weaker to avoid squeezing)
    nodes.forEach(node => {
      node.x *= 0.995
      node.y *= 0.995
    })
  }
  
  // Update viewBox to fit graph
  updateViewBox()
}

// Update viewBox to fit all nodes
function updateViewBox() {
  if (graphData.value.nodes.length === 0) return
  
  const padding = 100
  const xs = graphData.value.nodes.map(n => n.x)
  const ys = graphData.value.nodes.map(n => n.y)
  
  const minX = Math.min(...xs) - padding
  const maxX = Math.max(...xs) + padding
  const minY = Math.min(...ys) - padding
  const maxY = Math.max(...ys) + padding
  
  viewBox.value = {
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY
  }
}

// Get node position
function getNodePosition(nodeId: string) {
  const node = graphData.value.nodes.find(n => n.id === nodeId)
  return node ? { x: node.x || 0, y: node.y || 0 } : { x: 0, y: 0 }
}

// Get edge midpoint for label positioning
function getEdgeMidpoint(edge: any) {
  const source = getNodePosition(edge.source)
  const target = getNodePosition(edge.target)
  return {
    x: (source.x + target.x) / 2,
    y: (source.y + target.y) / 2
  }
}

// Get node radius based on type
function getNodeRadius(node: any) {
  const baseRadius = {
    root: 45,
    module: 35,
    concept: 25,
    application: 20,
    // Legacy
    core: 35,
    basic: 25,
    advanced: 25
  }
  const radius = baseRadius[node.type as keyof typeof baseRadius] || 25
  
  // Highlight selected or hovered node
  if (selectedNode.value?.id === node.id) return radius + 5
  if (hoverNode.value === node.id) return radius + 3
  return radius
}

// Get node CSS class
function getNodeClass(node: any) {
  const classes = [node.type]
  if (selectedNode.value?.id === node.id) classes.push('selected')
  if (hoverNode.value === node.id) classes.push('hovered')
  return classes.join(' ')
}

// Get edge CSS class
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

// Get node icon
function getNodeIcon(node: any) {
  const icons: Record<string, string> = {
    root: '★',
    module: '◆',
    concept: '●',
    theorem: 'π',
    method: 'ƒ',
    application: '⚡',
    // Legacy
    core: '★',
    basic: '●',
    advanced: '▲'
  }
  return icons[node.type] || '●'
}

// Get node type label
function getNodeTypeLabel(type: string) {
  const typeInfo = nodeTypes.find(t => t.value === type)
  return typeInfo?.label || type
}

// Select node
function selectNode(node: any) {
  selectedNode.value = node
}

// Deselect node
function deselectNode() {
  selectedNode.value = null
}

// Navigate to node in course
function navigateToNode(nodeId: string) {
  courseStore.scrollToNode(nodeId)
  ElMessage.success('已跳转到对应章节')
}

// Reset view
function resetView() {
  updateViewBox()
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

// Pan handling
function handleMouseDown(e: MouseEvent) {
  isDragging.value = true
  dragStart.value = { x: e.clientX, y: e.clientY }
  viewBoxStart.value = { x: viewBox.value.x, y: viewBox.value.y }
}

function handleMouseMove(e: MouseEvent) {
  if (!isDragging.value) return
  
  const dx = (e.clientX - dragStart.value.x) * viewBox.value.width / (graphContainer.value?.clientWidth || 800)
  const dy = (e.clientY - dragStart.value.y) * viewBox.value.height / (graphContainer.value?.clientHeight || 600)
  
  viewBox.value.x = viewBoxStart.value.x - dx
  viewBox.value.y = viewBoxStart.value.y - dy
}

function handleMouseUp() {
  isDragging.value = false
}
</script>

<style scoped>
.knowledge-graph-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 12px;
  overflow: hidden;
}

.graph-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: white;
  border-bottom: 1px solid #e2e8f0;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.graph-title {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #6366f1;
}

.toolbar-right {
  display: flex;
  gap: 8px;
}

.btn-generate,
.btn-refresh,
.btn-reset {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.btn-generate {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: white;
}

.btn-generate:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.btn-refresh {
  background: #f1f5f9;
  color: #475569;
}

.btn-refresh:hover:not(:disabled) {
  background: #e2e8f0;
}

.btn-reset {
  background: white;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.btn-reset:hover {
  background: #f8fafc;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.graph-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
  cursor: grab;
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
  stroke: #cbd5e1;
  transition: all 0.3s;
}

.edge-line.depends_on {
  stroke: #6366f1;
  stroke-dasharray: 5, 5;
}

.edge-line.contains {
  stroke: #10b981;
}

.edge-line.related {
  stroke: #f59e0b;
  stroke-dasharray: 3, 3;
}

.edge-line.applies_to {
  stroke: #ec4899;
}

.edge-line.highlighted {
  stroke-width: 3;
  filter: drop-shadow(0 0 4px rgba(99, 102, 241, 0.4));
}

.edge-line.dimmed {
  opacity: 0.3;
}

.edge-label-text {
  font-size: 10px;
  fill: #64748b;
}

/* Nodes */
.node-group {
  cursor: pointer;
  transition: all 0.3s;
}

.node-circle {
  transition: all 0.3s;
}

.node-circle.root {
  fill: #6366f1;
  stroke: #4f46e5;
}

.node-circle.module {
  fill: #8b5cf6;
  stroke: #7c3aed;
}

.node-circle.concept {
  fill: #10b981;
  stroke: #059669;
}

.node-circle.theorem {
  fill: #f59e0b;
  stroke: #d97706;
}

.node-circle.method {
  fill: #ec4899;
  stroke: #db2777;
}

.node-circle.core {
  fill: #6366f1;
  stroke: #4f46e5;
}

.node-circle.basic {
  fill: #10b981;
  stroke: #059669;
}

.node-circle.advanced {
  fill: #f59e0b;
  stroke: #d97706;
}

.node-circle.application {
  fill: #ec4899;
  stroke: #db2777;
}

.node-circle.selected {
  filter: drop-shadow(0 0 8px rgba(99, 102, 241, 0.6));
}

.node-circle.hovered {
  filter: drop-shadow(0 0 6px rgba(99, 102, 241, 0.4));
}

.node-icon {
  font-size: 16px;
  fill: white;
  pointer-events: none;
}

.node-label {
  font-size: 11px;
  fill: #334155;
  font-weight: 500;
  pointer-events: none;
}

/* Node Detail Panel */
.node-detail-panel {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 280px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
  border: 1px solid #e2e8f0;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-bottom: 1px solid #e2e8f0;
}

.panel-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.btn-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-close:hover {
  background: #e2e8f0;
  color: #334155;
}

.panel-content {
  padding: 16px;
}

.info-row {
  margin-bottom: 12px;
}

.info-row:last-child {
  margin-bottom: 0;
}

.info-label {
  font-size: 12px;
  color: #64748b;
  margin-right: 8px;
}

.info-value {
  font-size: 13px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 12px;
}

.type-root {
  background: #e0e7ff;
  color: #4338ca;
}

.type-module {
  background: #ede9fe;
  color: #7c3aed;
}

.type-concept {
  background: #d1fae5;
  color: #047857;
}

.type-theorem {
  background: #fef3c7;
  color: #b45309;
}

.type-method {
  background: #fce7f3;
  color: #be185d;
}

.type-core {
  background: #e0e7ff;
  color: #4338ca;
}

.type-basic {
  background: #d1fae5;
  color: #047857;
}

.type-advanced {
  background: #fef3c7;
  color: #b45309;
}

.type-application {
  background: #fce7f3;
  color: #be185d;
}

.info-description {
  font-size: 13px;
  color: #475569;
  line-height: 1.6;
  margin: 8px 0 0;
}

.btn-navigate {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 10px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-navigate:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

/* Legend */
.graph-legend {
  position: absolute;
  bottom: 16px;
  left: 16px;
  background: white;
  border-radius: 10px;
  padding: 12px 14px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  border: 1px solid #e2e8f0;
}

.legend-title {
  font-size: 12px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 8px;
}

.legend-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.legend-dot.type-core {
  background: #6366f1;
}

.legend-dot.type-basic {
  background: #10b981;
}

.legend-dot.type-advanced {
  background: #f59e0b;
}

.legend-dot.type-application {
  background: #ec4899;
}

.legend-label {
  font-size: 12px;
  color: #64748b;
}

/* Stats */
.graph-stats {
  position: absolute;
  bottom: 16px;
  right: 16px;
  display: flex;
  gap: 12px;
  background: white;
  padding: 8px 14px;
  border-radius: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  font-size: 12px;
  color: #64748b;
}

/* Transitions */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateX(20px);
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
  gap: 16px;
  z-index: 10;
}

.empty-icon {
  font-size: 48px;
  color: #cbd5e1;
}

.empty-text {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}

.btn-generate-large {
  padding: 10px 24px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: white;
  border: none;
  border-radius: 24px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
  transition: all 0.2s;
}

.btn-generate-large:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4);
}
</style>
