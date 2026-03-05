<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="courseStore.showKnowledgeGraph" class="kg-modal-overlay" @click.self="handleClose">
        <div class="kg-modal-container">
          <!-- Header -->
          <div class="kg-modal-header">
            <div class="kg-header-left">
              <div class="kg-title-wrapper">
                <div class="kg-title-icon">
                  <el-icon :size="20"><Share /></el-icon>
                </div>
                <div>
                  <h2 class="kg-title">知识图谱</h2>
                  <p class="kg-subtitle" v-if="hasGraph">{{ graphData.nodes.length }} 个概念 · {{ graphData.edges.length }} 条关系</p>
                </div>
              </div>
            </div>
            
            <div class="kg-header-center" v-if="hasGraph">
              <div class="kg-search-wrapper">
                <el-icon class="kg-search-icon"><Search /></el-icon>
                <input
                  v-model="searchQuery"
                  type="text"
                  placeholder="搜索概念..."
                  class="kg-search-input"
                  @input="handleSearchInput"
                  @keyup.enter="handleSearch"
                />
                <button v-if="searchQuery" class="kg-search-clear" @click="clearSearch">
                  <el-icon><Close /></el-icon>
                </button>
              </div>
            </div>
            
            <div class="kg-header-right">
              <template v-if="hasGraph">
                <button class="kg-action-btn" @click="toggleMinimap" :class="{ active: showMinimap }" title="迷你地图">
                  <el-icon><MapLocation /></el-icon>
                </button>
                <button class="kg-action-btn" @click="resetView" title="重置视图">
                  <el-icon><Compass /></el-icon>
                </button>
                <button class="kg-action-btn" @click="downloadImage" title="导出图片">
                  <el-icon><Download /></el-icon>
                </button>
              </template>
              <button 
                v-if="!hasGraph" 
                class="kg-btn kg-btn-primary" 
                :disabled="loading" 
                @click="generateGraph"
              >
                <el-icon :class="{ 'is-loading': loading }"><MagicStick /></el-icon>
                {{ loading ? '生成中...' : '生成图谱' }}
              </button>
              <button 
                v-else 
                class="kg-btn kg-btn-secondary" 
                :disabled="loading" 
                @click="generateGraph"
              >
                <el-icon :class="{ 'is-loading': loading }"><Refresh /></el-icon>
                重新生成
              </button>
              <button class="kg-close-btn" @click="handleClose">
                <el-icon :size="18"><Close /></el-icon>
              </button>
            </div>
          </div>

          <!-- Main Content -->
          <div class="kg-modal-body">
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
                  <!-- Grid Pattern -->
                  <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
                    <circle cx="15" cy="15" r="1" fill="#e2e8f0"/>
                  </pattern>
                  
                  <!-- Node Shadow -->
                  <filter id="nodeShadow" x="-50%" y="-50%" width="200%" height="200%">
                    <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000" flood-opacity="0.1"/>
                  </filter>
                  
                  <!-- Glow Effect -->
                  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                    <feDropShadow dx="0" dy="0" stdDeviation="8" flood-color="#6366f1" flood-opacity="0.5"/>
                  </filter>
                  
                  <!-- Arrow Markers -->
                  <marker id="arrow-prerequisite" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#f59e0b"/>
                  </marker>
                  <marker id="arrow-derives" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#8b5cf6"/>
                  </marker>
                  <marker id="arrow-applies" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#10b981"/>
                  </marker>
                  <marker id="arrow-contrasts" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#ef4444"/>
                  </marker>
                  <marker id="arrow-default" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8"/>
                  </marker>
                </defs>
                
                <rect width="100%" height="100%" fill="url(#grid)"/>
                
                <!-- Edges Layer -->
                <g class="kg-edges-layer">
                  <g v-for="edge in graphData.edges" :key="edge.source + '-' + edge.target">
                    <!-- Edge Path -->
                    <path
                      :d="getEdgePath(edge)"
                      class="kg-edge"
                      :class="getEdgeClass(edge)"
                      :marker-end="getArrowMarker(edge.relation)"
                    />
                    <!-- Edge Label -->
                    <text
                      v-if="showEdgeLabels && getEdgeMidpoint(edge)"
                      :x="getEdgeMidpoint(edge).x"
                      :y="getEdgeMidpoint(edge).y"
                      class="kg-edge-label"
                    >{{ getRelationLabel(edge.relation) }}</text>
                  </g>
                </g>
                
                <!-- Nodes Layer -->
                <g class="kg-nodes-layer">
                  <g
                    v-for="node in graphData.nodes"
                    :key="node.id"
                    class="kg-node-group"
                    :class="{
                      'kg-node-selected': selectedNode?.id === node.id,
                      'kg-node-highlighted': highlightedNodes.includes(node.id),
                      'kg-node-dimmed': dimmedNodes.includes(node.id),
                      'kg-node-root': node.type === 'root'
                    }"
                    :transform="`translate(${node.x}, ${node.y})`"
                    @click.stop="selectNode(node)"
                    @mouseenter="hoverNode(node)"
                    @mouseleave="unhoverNode"
                  >
                    <!-- Node Background - Simple rounded rectangle -->
                    <rect
                      :x="-getNodeWidth(node) / 2"
                      :y="-18"
                      :width="getNodeWidth(node)"
                      :height="36"
                      rx="18"
                      class="kg-node-bg"
                      :style="getNodeStyle(node)"
                    />
                    
                    <!-- Node Label -->
                    <text
                      :x="0"
                      y="5"
                      class="kg-node-label"
                      :style="{ fill: node.type === 'root' ? '#fff' : getNodeColor(node, 'accent') }"
                    >{{ node.label }}</text>
                  </g>
                </g>
              </svg>

              <!-- Empty State -->
              <div v-if="!hasGraph && !loading" class="kg-empty-state">
                <div class="kg-empty-illustration">
                  <div class="kg-empty-circle">
                    <el-icon :size="48"><Share /></el-icon>
                  </div>
                  <div class="kg-empty-dots">
                    <span></span><span></span><span></span>
                  </div>
                </div>
                <h3 class="kg-empty-title">暂无知识图谱</h3>
                <p class="kg-empty-desc">生成知识图谱，可视化课程概念关系</p>
                <button class="kg-btn kg-btn-primary kg-btn-large" @click="generateGraph">
                  <el-icon><MagicStick /></el-icon>
                  立即生成
                </button>
              </div>
              
              <!-- Loading State -->
              <div v-if="loading" class="kg-loading-state">
                <div class="kg-loading-spinner">
                  <div class="kg-spinner-ring"></div>
                  <div class="kg-spinner-ring"></div>
                  <div class="kg-spinner-ring"></div>
                </div>
                <p class="kg-loading-text">正在生成知识图谱...</p>
                <p class="kg-loading-hint">AI 正在分析课程内容并构建概念关系</p>
              </div>

              <!-- Node Detail Panel -->
              <Transition name="slide-right">
                <div v-if="selectedNode" class="kg-detail-panel">
                  <div class="kg-detail-header">
                    <div class="kg-detail-type" :style="{ background: getNodeColor(selectedNode, 'accent') + '15', color: getNodeColor(selectedNode, 'accent') }">
                      {{ getNodeIcon(selectedNode.type) }} {{ getTypeLabel(selectedNode.type) }}
                    </div>
                    <button class="kg-detail-close" @click="deselectNode">
                      <el-icon><Close /></el-icon>
                    </button>
                  </div>
                  
                  <h3 class="kg-detail-title">{{ selectedNode.label }}</h3>
                  
                  <div v-if="selectedNode.description" class="kg-detail-section">
                    <h4 class="kg-detail-section-title">描述</h4>
                    <p class="kg-detail-description">{{ selectedNode.description }}</p>
                  </div>
                  
                  <!-- Related Nodes -->
                  <div v-if="relatedNodes.length > 0" class="kg-detail-section">
                    <h4 class="kg-detail-section-title">相关概念</h4>
                    <div class="kg-related-nodes">
                      <button 
                        v-for="rel in relatedNodes" 
                        :key="rel.node.id"
                        class="kg-related-node"
                        @click="selectNode(rel.node)"
                      >
                        <span class="kg-related-icon" :style="{ background: getNodeColor(rel.node, 'accent') + '15' }">
                          {{ getNodeIcon(rel.node.type) }}
                        </span>
                        <div class="kg-related-info">
                          <span class="kg-related-label">{{ rel.node.label }}</span>
                          <span class="kg-related-relation">{{ getRelationLabel(rel.relation) }}</span>
                        </div>
                        <el-icon class="kg-related-arrow"><ArrowRight /></el-icon>
                      </button>
                    </div>
                  </div>
                  
                  <div class="kg-detail-actions">
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
              
              <!-- Minimap -->
              <Transition name="fade">
                <div v-if="showMinimap && hasGraph" class="kg-minimap">
                  <svg :viewBox="minimapViewBox" class="kg-minimap-svg">
                    <rect width="100%" height="100%" fill="#f8fafc"/>
                    <!-- Minimap Nodes -->
                    <circle
                      v-for="node in graphData.nodes"
                      :key="'mini-' + node.id"
                      :cx="node.x"
                      :cy="node.y"
                      r="4"
                      :fill="getNodeColor(node, 'accent')"
                      :opacity="selectedNode?.id === node.id ? 1 : 0.5"
                    />
                    <!-- Viewport Indicator -->
                    <rect
                      :x="viewBox.x"
                      :y="viewBox.y"
                      :width="viewBox.width"
                      :height="viewBox.height"
                      fill="rgba(99, 102, 241, 0.1)"
                      stroke="#6366f1"
                      stroke-width="2"
                      rx="4"
                    />
                  </svg>
                </div>
              </Transition>
            </div>

            <!-- Legend -->
            <div v-if="hasGraph" class="kg-legend">
              <div class="kg-legend-header">
                <span class="kg-legend-title">图例</span>
                <button class="kg-legend-toggle" @click="showEdgeLabels = !showEdgeLabels">
                  <el-icon :size="14"><View /></el-icon>
                  {{ showEdgeLabels ? '隐藏' : '显示' }}关系
                </button>
              </div>
              <div class="kg-legend-items">
                <div v-for="type in nodeTypes" :key="type.value" class="kg-legend-item">
                  <span class="kg-legend-dot" :style="{ background: type.color }"></span>
                  <span class="kg-legend-label">{{ type.label }}</span>
                </div>
              </div>
            </div>

            <!-- Zoom Controls -->
            <div v-if="hasGraph" class="kg-zoom-controls">
              <button class="kg-zoom-btn" @click="zoomIn" title="放大">
                <el-icon><Plus /></el-icon>
              </button>
              <div class="kg-zoom-level">
                <span>{{ Math.round(zoomLevel) }}%</span>
              </div>
              <button class="kg-zoom-btn" @click="zoomOut" title="缩小">
                <el-icon><Minus /></el-icon>
              </button>
              <div class="kg-zoom-divider"></div>
              <button class="kg-zoom-btn" @click="fitView" title="适应视图">
                <el-icon><FullScreen /></el-icon>
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useCourseStore } from '../stores/course'
import { ElMessage } from 'element-plus'
import { 
  Share, Search, Close, MagicStick, Refresh, Download, MapLocation,
  Compass, Position, Plus, Minus, FullScreen, ArrowRight, View
} from '@element-plus/icons-vue'
import http from '../utils/http'

const courseStore = useCourseStore()

// State
const loading = ref(false)
const graphData = ref<{ nodes: any[], edges: any[] }>({ nodes: [], edges: [] })
const selectedNode = ref<any>(null)
const hoveredNodeId = ref<string | null>(null)
const searchQuery = ref('')
const canvasRef = ref<HTMLElement | null>(null)
const showMinimap = ref(true)
const showEdgeLabels = ref(false)
const highlightedNodes = ref<string[]>([])
const dimmedNodes = ref<string[]>([])

// ViewBox
const viewBox = ref({ x: 0, y: 0, width: 1000, height: 700 })
const viewBoxStr = computed(() => `${viewBox.value.x} ${viewBox.value.y} ${viewBox.value.width} ${viewBox.value.height}`)
const zoomLevel = computed(() => (1000 / viewBox.value.width) * 100)
const minimapViewBox = computed(() => {
  const nodes = graphData.value.nodes
  if (!nodes.length) return '0 0 1000 700'
  const padding = 100
  const xs = nodes.map(n => n.x)
  const ys = nodes.map(n => n.y)
  const minX = Math.min(...xs) - padding
  const minY = Math.min(...ys) - padding
  const width = Math.max(...xs) - minX + padding * 2
  const height = Math.max(...ys) - minY + padding * 2
  return `${minX} ${minY} ${width} ${height}`
})

// Panning
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0 })
const viewBoxStart = ref({ x: 0, y: 0 })

// Node types with icons
const nodeTypes = [
  { value: 'root', label: '核心主题', color: '#4f46e5', icon: '🎯' },
  { value: 'concept', label: '核心概念', color: '#059669', icon: '💡' },
  { value: 'theorem', label: '关键定理', color: '#d97706', icon: '📐' },
  { value: 'method', label: '核心方法', color: '#db2777', icon: '⚙️' }
]

// Relation types
const relationTypes: Record<string, { label: string; color: string }> = {
  'prerequisite': { label: '前置知识', color: '#f59e0b' },
  'derives': { label: '推导', color: '#8b5cf6' },
  'applies_to': { label: '应用', color: '#10b981' },
  'contrasts_with': { label: '对比', color: '#ef4444' },
  'extends': { label: '扩展', color: '#06b6d4' },
  'implements': { label: '实现', color: '#ec4899' },
  'leads_to': { label: '导致', color: '#f97316' }
}

const hasGraph = computed(() => graphData.value.nodes.length > 0)

// Related nodes for selected node
const relatedNodes = computed(() => {
  if (!selectedNode.value) return []
  
  const related: { node: any; relation: string }[] = []
  const nodeId = selectedNode.value.id
  
  graphData.value.edges.forEach(edge => {
    if (edge.source === nodeId) {
      const targetNode = graphData.value.nodes.find(n => n.id === edge.target)
      if (targetNode) related.push({ node: targetNode, relation: edge.relation })
    } else if (edge.target === nodeId) {
      const sourceNode = graphData.value.nodes.find(n => n.id === edge.source)
      if (sourceNode) related.push({ node: sourceNode, relation: edge.relation })
    }
  })
  
  return related.slice(0, 5)
})

// Close
const handleClose = () => {
  courseStore.showKnowledgeGraph = false
}

// Toggle minimap
const toggleMinimap = () => {
  showMinimap.value = !showMinimap.value
}

// Load graph
const loadGraph = async () => {
  if (!courseStore.currentCourseId) return
  
  try {
    const res = await http.get(`/courses/${courseStore.currentCourseId}/knowledge_graph`)
    const data = res.data
    
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
    const res = await http.post(`/courses/${courseStore.currentCourseId}/knowledge_graph`)
    const data = res.data
    
    if (data.status === 'success') {
      graphData.value = data.data
      layoutGraph()
      ElMessage.success('知识图谱生成成功')
    } else {
      ElMessage.error('生成失败: ' + (data.message || '未知错误'))
    }
  } catch (e: any) {
    console.error('Failed to generate graph:', e)
    ElMessage.error('生成失败: ' + (e.message || '网络错误'))
  } finally {
    loading.value = false
  }
}

// Layout algorithm - XMind-style radial tree layout
const layoutGraph = () => {
  const nodes = graphData.value.nodes
  const edges = graphData.value.edges
  if (!nodes.length) return

  const CANVAS_WIDTH = 1400
  const CANVAS_HEIGHT = 900
  const CENTER_X = CANVAS_WIDTH / 2
  const CENTER_Y = CANVAS_HEIGHT / 2

  // Build adjacency lists
  const children: Record<string, string[]> = {}
  const parents: Record<string, string[]> = {}
  nodes.forEach(n => { children[n.id] = []; parents[n.id] = [] })
  edges.forEach(e => {
    if (children[e.source]) children[e.source].push(e.target)
    if (parents[e.target]) parents[e.target].push(e.source)
  })

  // Find root node
  const root = nodes.find(n => n.type === 'root') || nodes[0]
  if (!root) return

  // Position root at center
  root.x = CENTER_X
  root.y = CENTER_Y

  // Get direct children of root (main branches)
  const mainBranches = children[root.id] || []
  
  // Calculate angles for main branches (spread evenly)
  const branchCount = mainBranches.length
  const angleStep = (2 * Math.PI) / Math.max(branchCount, 1)
  
  // Position main branches in a circle around root
  const mainBranchNodes: string[] = []
  mainBranches.forEach((nodeId, index) => {
    const node = nodes.find(n => n.id === nodeId)
    if (!node) return
    
    mainBranchNodes.push(nodeId)
    
    // Calculate position with staggered radius
    const angle = -Math.PI / 2 + index * angleStep
    const radius = 280
    
    node.x = CENTER_X + Math.cos(angle) * radius
    node.y = CENTER_Y + Math.sin(angle) * radius
    
    // Position sub-branches
    const subBranches = children[nodeId] || []
    const subAngleSpread = angleStep * 0.8
    const subAngleStart = angle - subAngleSpread / 2
    
    subBranches.forEach((subNodeId, subIndex) => {
      const subNode = nodes.find(n => n.id === subNodeId)
      if (!subNode) return
      
      const subAngle = subAngleStart + (subIndex + 0.5) * (subAngleSpread / Math.max(subBranches.length, 1))
      const subRadius = 200
      
      subNode.x = node.x + Math.cos(subAngle) * subRadius
      subNode.y = node.y + Math.sin(subAngle) * subRadius
      
      // Position leaf nodes
      const leafNodes = children[subNodeId] || []
      leafNodes.forEach((leafId, leafIndex) => {
        const leafNode = nodes.find(n => n.id === leafId)
        if (!leafNode) return
        
        const leafAngle = subAngle + (leafIndex - (leafNodes.length - 1) / 2) * 0.3
        const leafRadius = 150
        
        leafNode.x = subNode.x + Math.cos(leafAngle) * leafRadius
        leafNode.y = subNode.y + Math.sin(leafAngle) * leafRadius
      })
    })
  })

  // Handle unconnected nodes (place them on the periphery)
  const positionedIds = new Set([root.id, ...mainBranchNodes])
  nodes.forEach(n => positionedIds.add(n.id))
  
  const unconnectedNodes = nodes.filter(n => 
    n.x === undefined || n.y === undefined
  )
  
  unconnectedNodes.forEach((node, index) => {
    const angle = (index / unconnectedNodes.length) * 2 * Math.PI
    const radius = 450
    node.x = CENTER_X + Math.cos(angle) * radius
    node.y = CENTER_Y + Math.sin(angle) * radius
  })

  // Apply gentle force adjustment to avoid overlaps
  applyGentleForce()

  fitView()
}

// Gentle force to separate overlapping nodes
const applyGentleForce = () => {
  const nodes = graphData.value.nodes
  const iterations = 30
  const MIN_DIST = 100
  
  for (let i = 0; i < iterations; i++) {
    for (let j = 0; j < nodes.length; j++) {
      for (let k = j + 1; k < nodes.length; k++) {
        const dx = nodes[k].x - nodes[j].x
        const dy = nodes[k].y - nodes[j].y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        
        if (dist < MIN_DIST) {
          const force = (MIN_DIST - dist) * 0.1
          const fx = (dx / dist) * force
          const fy = (dy / dist) * force
          
          nodes[j].x -= fx
          nodes[j].y -= fy
          nodes[k].x += fx
          nodes[k].y += fy
        }
      }
    }
  }
}

// Fit view to nodes
const fitView = () => {
  const nodes = graphData.value.nodes
  if (!nodes.length) return

  const padding = 120
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
const getNodeWidth = (node: any) => {
  const baseWidth = node.type === 'root' ? 140 : 100
  const textWidth = (node.label?.length || 0) * 14
  return Math.max(baseWidth, textWidth + 40)
}
const getNodeIcon = (type: string) => nodeTypes.find(t => t.value === type)?.icon || '📌'

const getNodeColor = (node: any, part: string = 'bg') => {
  const color = nodeTypes.find(t => t.value === node.type)?.color || '#94a3b8'
  if (part === 'bg') return color + '10'
  if (part === 'border') return color + '40'
  if (part === 'accent') return color
  return color
}

const getNodeStyle = (node: any) => {
  const color = getNodeColor(node, 'accent')
  if (node.type === 'root') {
    return {
      fill: color,
      stroke: 'none'
    }
  }
  return {
    fill: color + '15',
    stroke: color + '40'
  }
}

const getTypeLabel = (type: string) => nodeTypes.find(t => t.value === type)?.label || type
const getRelationLabel = (relation: string) => relationTypes[relation]?.label || relation

// Edge helpers
const getEdgePath = (edge: any) => {
  const source = graphData.value.nodes.find(n => n.id === edge.source)
  const target = graphData.value.nodes.find(n => n.id === edge.target)
  if (!source || !target) return ''
  
  const dx = target.x - source.x
  const dy = target.y - source.y
  const dist = Math.sqrt(dx * dx + dy * dy)
  
  // Simple curved path with gentle curve
  const curvature = 0.15
  const cx = (source.x + target.x) / 2 - dy * curvature
  const cy = (source.y + target.y) / 2 + dx * curvature
  
  return `M ${source.x} ${source.y} Q ${cx} ${cy} ${target.x} ${target.y}`
}

const getEdgeMidpoint = (edge: any) => {
  const source = graphData.value.nodes.find(n => n.id === edge.source)
  const target = graphData.value.nodes.find(n => n.id === edge.target)
  if (!source || !target) return null
  
  return {
    x: (source.x + target.x) / 2,
    y: (source.y + target.y) / 2 - 10
  }
}

const getEdgeClass = (edge: any) => {
  const classes = []
  if (selectedNode.value) {
    const isConnected = edge.source === selectedNode.value.id || edge.target === selectedNode.value.id
    classes.push(isConnected ? 'kg-edge-highlight' : 'kg-edge-dim')
  }
  if (hoveredNodeId.value) {
    const isHovered = edge.source === hoveredNodeId.value || edge.target === hoveredNodeId.value
    if (isHovered) classes.push('kg-edge-hover')
  }
  return classes.join(' ')
}

const getArrowMarker = (relation: string) => {
  if (relation === 'prerequisite') return 'url(#arrow-prerequisite)'
  if (relation === 'derives') return 'url(#arrow-derives)'
  if (relation === 'applies_to') return 'url(#arrow-applies)'
  if (relation === 'contrasts_with') return 'url(#arrow-contrasts)'
  return 'url(#arrow-default)'
}

// Selection
const selectNode = (node: any) => { 
  selectedNode.value = node 
}

const deselectNode = () => { 
  selectedNode.value = null 
}

// Hover
const hoverNode = (node: any) => {
  hoveredNodeId.value = node.id
}

const unhoverNode = () => {
  hoveredNodeId.value = null
}

// Navigation
const navigateToNode = (nodeId: string) => {
  courseStore.scrollToNode(nodeId)
  handleClose()
  ElMessage.success('已跳转到对应章节')
}

// Search
const handleSearchInput = () => {
  if (!searchQuery.value.trim()) {
    highlightedNodes.value = []
    dimmedNodes.value = []
    return
  }
  
  const query = searchQuery.value.toLowerCase()
  highlightedNodes.value = graphData.value.nodes
    .filter(n => n.label?.toLowerCase().includes(query))
    .map(n => n.id)
  dimmedNodes.value = graphData.value.nodes
    .filter(n => !n.label?.toLowerCase().includes(query))
    .map(n => n.id)
}

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
      x: found.x - 200,
      y: found.y - 150,
      width: 400,
      height: 300
    }
  } else {
    ElMessage.info('未找到匹配的节点')
  }
}

const clearSearch = () => {
  searchQuery.value = ''
  highlightedNodes.value = []
  dimmedNodes.value = []
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
  viewBox.value.width *= scale
  viewBox.value.height *= scale
}

// Pan
const startPan = (e: MouseEvent) => {
  if (e.target !== canvasRef.value?.querySelector('svg')) return
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

// Keyboard shortcuts
const handleKeydown = (e: KeyboardEvent) => {
  if (!courseStore.showKnowledgeGraph) return
  
  if (e.key === 'Escape') {
    if (selectedNode.value) {
      deselectNode()
    } else {
      handleClose()
    }
  } else if (e.key === 'f' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault()
    const searchInput = document.querySelector('.kg-search-input') as HTMLInputElement
    searchInput?.focus()
  }
}

// Watch
watch(() => courseStore.showKnowledgeGraph, (show) => {
  if (show) {
    loadGraph()
    document.addEventListener('keydown', handleKeydown)
  } else {
    document.removeEventListener('keydown', handleKeydown)
    selectedNode.value = null
    searchQuery.value = ''
  }
})

watch(() => courseStore.currentCourseId, () => {
  if (courseStore.showKnowledgeGraph) loadGraph()
})
</script>

<style scoped>
/* Modal Overlay */
.kg-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

/* Modal Container */
.kg-modal-container {
  width: 100%;
  height: 100%;
  max-width: 1400px;
  max-height: 900px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 24px;
  box-shadow: 
    0 25px 80px rgba(0, 0, 0, 0.25),
    0 0 0 1px rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: modalSlideIn 0.3s ease-out;
}

@keyframes modalSlideIn {
  from {
    opacity: 0;
    transform: scale(0.95) translateY(20px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

/* Header */
.kg-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  background: white;
  border-bottom: 1px solid #e2e8f0;
  gap: 20px;
  flex-shrink: 0;
}

.kg-header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.kg-title-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
}

.kg-title-icon {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.kg-title {
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
}

.kg-subtitle {
  font-size: 12px;
  color: #64748b;
  margin: 2px 0 0 0;
}

.kg-header-center {
  flex: 1;
  max-width: 400px;
}

.kg-search-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.kg-search-icon {
  position: absolute;
  left: 14px;
  color: #94a3b8;
}

.kg-search-input {
  width: 100%;
  padding: 12px 40px;
  border: 2px solid #e2e8f0;
  border-radius: 14px;
  font-size: 14px;
  background: #f8fafc;
  transition: all 0.2s;
}

.kg-search-input:focus {
  outline: none;
  border-color: #6366f1;
  background: white;
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
}

.kg-search-clear {
  position: absolute;
  right: 10px;
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  display: flex;
  border-radius: 6px;
  transition: all 0.2s;
}

.kg-search-clear:hover {
  background: #f1f5f9;
  color: #64748b;
}

.kg-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.kg-action-btn {
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

.kg-action-btn:hover {
  background: #e2e8f0;
  color: #334155;
}

.kg-action-btn.active {
  background: #6366f1;
  color: white;
}

.kg-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.kg-btn-primary {
  background: linear-gradient(135deg, #4f46e5, #6366f1);
  color: white;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.kg-btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
}

.kg-btn-secondary {
  background: white;
  color: #475569;
  border: 2px solid #e2e8f0;
}

.kg-btn-secondary:hover:not(:disabled) {
  border-color: #cbd5e1;
  background: #f8fafc;
}

.kg-btn-large {
  padding: 16px 32px;
  font-size: 15px;
  border-radius: 16px;
}

.kg-btn-block {
  width: 100%;
  justify-content: center;
}

.kg-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.kg-close-btn {
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
  margin-left: 8px;
}

.kg-close-btn:hover {
  background: #fee2e2;
  color: #ef4444;
}

/* Body */
.kg-modal-body {
  flex: 1;
  position: relative;
  overflow: hidden;
}

/* Canvas */
.kg-canvas {
  width: 100%;
  height: 100%;
  position: relative;
  cursor: grab;
  background: 
    radial-gradient(circle at 50% 50%, rgba(99, 102, 241, 0.03) 0%, transparent 50%);
}

.kg-canvas:active {
  cursor: grabbing;
}

.kg-svg {
  width: 100%;
  height: 100%;
}

/* Edges */
.kg-edge {
  fill: none;
  stroke: #cbd5e1;
  stroke-width: 2;
  transition: all 0.3s ease;
}

.kg-edge-highlight {
  stroke: #6366f1;
  stroke-width: 3;
}

.kg-edge-dim {
  stroke: #e2e8f0;
  opacity: 0.3;
}

.kg-edge-hover {
  stroke: #6366f1;
  stroke-width: 2.5;
}

.kg-edge-label {
  font-size: 10px;
  fill: #64748b;
  text-anchor: middle;
  pointer-events: none;
  background: white;
  padding: 2px 6px;
  border-radius: 4px;
}

/* Nodes */
.kg-node-group {
  cursor: pointer;
  transition: filter 0.2s;
}

.kg-node-bg {
  stroke-width: 2;
  transition: all 0.2s;
}

.kg-node-group:hover .kg-node-bg {
  filter: url(#nodeShadow);
}

.kg-node-selected .kg-node-bg {
  stroke-width: 3;
  filter: url(#glow);
}

.kg-node-highlighted .kg-node-bg {
  stroke-width: 3;
}

.kg-node-dimmed {
  opacity: 0.3;
}

.kg-node-icon {
  font-size: 12px;
  text-anchor: middle;
  dominant-baseline: middle;
}

.kg-node-label {
  font-size: 13px;
  font-weight: 600;
  fill: #1e293b;
  font-family: system-ui, -apple-system, sans-serif;
  pointer-events: none;
  dominant-baseline: middle;
}

/* Empty State */
.kg-empty-state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 24px;
}

.kg-empty-illustration {
  position: relative;
}

.kg-empty-circle {
  width: 120px;
  height: 120px;
  background: linear-gradient(135deg, #eef2ff, #e0e7ff);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6366f1;
}

.kg-empty-dots {
  position: absolute;
  bottom: -20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 8px;
}

.kg-empty-dots span {
  width: 8px;
  height: 8px;
  background: #cbd5e1;
  border-radius: 50%;
  animation: bounce 1.4s ease-in-out infinite;
}

.kg-empty-dots span:nth-child(1) { animation-delay: 0s; }
.kg-empty-dots span:nth-child(2) { animation-delay: 0.2s; }
.kg-empty-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-8px); }
}

.kg-empty-title {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
}

.kg-empty-desc {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}

/* Loading State */
.kg-loading-state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
}

.kg-loading-spinner {
  position: relative;
  width: 60px;
  height: 60px;
}

.kg-spinner-ring {
  position: absolute;
  inset: 0;
  border: 3px solid #e2e8f0;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.kg-spinner-ring:nth-child(2) {
  inset: 8px;
  border-top-color: #8b5cf6;
  animation-duration: 1.5s;
  animation-direction: reverse;
}

.kg-spinner-ring:nth-child(3) {
  inset: 16px;
  border-top-color: #a78bfa;
  animation-duration: 2s;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.kg-loading-text {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.kg-loading-hint {
  font-size: 13px;
  color: #64748b;
  margin: 0;
}

/* Detail Panel */
.kg-detail-panel {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 340px;
  background: white;
  border-radius: 20px;
  box-shadow: 
    0 20px 60px rgba(0, 0, 0, 0.15),
    0 0 0 1px rgba(0, 0, 0, 0.05);
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

.kg-detail-type {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 8px;
}

.kg-detail-close {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  border: none;
  background: #f1f5f9;
  color: #64748b;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.kg-detail-close:hover {
  background: #e2e8f0;
  color: #334155;
}

.kg-detail-title {
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
  padding: 0 20px;
  padding-top: 16px;
}

.kg-detail-section {
  padding: 16px 20px;
}

.kg-detail-section-title {
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 10px 0;
}

.kg-detail-description {
  font-size: 14px;
  color: #475569;
  line-height: 1.6;
  margin: 0;
  background: #f8fafc;
  padding: 14px;
  border-radius: 12px;
}

.kg-related-nodes {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kg-related-node {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: #f8fafc;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  width: 100%;
  text-align: left;
}

.kg-related-node:hover {
  background: #f1f5f9;
  transform: translateX(4px);
}

.kg-related-icon {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

.kg-related-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.kg-related-label {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
}

.kg-related-relation {
  font-size: 11px;
  color: #64748b;
}

.kg-related-arrow {
  color: #94a3b8;
}

.kg-detail-actions {
  padding: 20px;
  border-top: 1px solid #f1f5f9;
}

/* Minimap */
.kg-minimap {
  position: absolute;
  bottom: 20px;
  left: 20px;
  width: 200px;
  height: 140px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  z-index: 10;
}

.kg-minimap-svg {
  width: 100%;
  height: 100%;
}

/* Legend */
.kg-legend {
  position: absolute;
  bottom: 20px;
  left: 240px;
  background: white;
  border-radius: 16px;
  padding: 16px 20px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
  z-index: 10;
}

.kg-legend-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.kg-legend-title {
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.kg-legend-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  font-size: 11px;
  color: #6366f1;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: all 0.2s;
}

.kg-legend-toggle:hover {
  background: #eef2ff;
}

.kg-legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.kg-legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.kg-legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 4px;
}

.kg-legend-label {
  font-size: 12px;
  color: #475569;
}

/* Zoom Controls */
.kg-zoom-controls {
  position: absolute;
  bottom: 20px;
  right: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  background: white;
  padding: 8px;
  border-radius: 16px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
  z-index: 10;
}

.kg-zoom-btn {
  width: 40px;
  height: 40px;
  border-radius: 12px;
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
  padding: 4px 0;
}

.kg-zoom-divider {
  width: 24px;
  height: 1px;
  background: #e2e8f0;
  margin: 4px 0;
}

/* Transitions */
.modal-enter-active,
.modal-leave-active {
  transition: all 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .kg-modal-container,
.modal-leave-to .kg-modal-container {
  transform: scale(0.95) translateY(20px);
}

.slide-right-enter-active,
.slide-right-leave-active {
  transition: all 0.3s ease;
}

.slide-right-enter-from,
.slide-right-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Responsive */
@media (max-width: 1024px) {
  .kg-modal-overlay {
    padding: 20px;
  }
  
  .kg-modal-container {
    max-height: none;
    border-radius: 20px;
  }
  
  .kg-header-center {
    display: none;
  }
  
  .kg-detail-panel {
    width: 300px;
  }
  
  .kg-minimap {
    display: none;
  }
  
  .kg-legend {
    left: 20px;
    bottom: 80px;
  }
}

@media (max-width: 640px) {
  .kg-modal-overlay {
    padding: 0;
  }
  
  .kg-modal-container {
    border-radius: 0;
    max-height: none;
  }
  
  .kg-modal-header {
    padding: 16px;
    flex-wrap: wrap;
  }
  
  .kg-header-left {
    order: 1;
  }
  
  .kg-header-right {
    order: 2;
    margin-left: auto;
  }
  
  .kg-detail-panel {
    position: fixed;
    inset: auto;
    bottom: 0;
    left: 0;
    right: 0;
    width: 100%;
    border-radius: 20px 20px 0 0;
    max-height: 60vh;
    overflow-y: auto;
  }
  
  .kg-legend {
    display: none;
  }
  
  .kg-zoom-controls {
    bottom: 80px;
  }
}
</style>
