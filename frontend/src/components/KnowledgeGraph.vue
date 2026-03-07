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
                  <h2 class="kg-title">Knowledge Graph</h2>
                  <p class="kg-subtitle" v-if="hasGraph">{{ graphData.nodes.length }}  concepts / {{ graphData.edges.length }}  relations</p>
                </div>
              </div>
            </div>
            <div class="kg-header-center" v-if="hasGraph">
              <div class="kg-search-wrapper">
                <el-icon class="kg-search-icon"><Search /></el-icon>
                <input v-model="searchQuery" type="text" placeholder="Search..." class="kg-search-input"
                  @input="handleSearchInput" @keyup.enter="handleSearch" />
                <button v-if="searchQuery" class="kg-search-clear" @click="clearSearch">
                  <el-icon><Close /></el-icon>
                </button>
              </div>
            </div>
            <div class="kg-header-right">
              <template v-if="hasGraph">
                <button class="kg-action-btn" @click="toggleMinimap" :class="{ active: showMinimap }" title="????">
                  <el-icon><MapLocation /></el-icon>
                </button>
                <button class="kg-action-btn" @click="resetView" title="Reset">
                  <el-icon><Compass /></el-icon>
                </button>
                <button class="kg-action-btn" @click="downloadImage" title="Export">
                  <el-icon><Download /></el-icon>
                </button>
              </template>
              <button v-if="!hasGraph" class="kg-btn kg-btn-primary" :disabled="loading" @click="generateGraph">
                <el-icon :class="{ 'is-loading': loading }"><MagicStick /></el-icon>
                {{ loading ? 'Generating...' : 'Generate' }}
              </button>
              <button v-else class="kg-btn kg-btn-secondary" :disabled="loading" @click="generateGraph">
                <el-icon :class="{ 'is-loading': loading }"><Refresh /></el-icon>
                Regenerate
              </button>
              <button class="kg-close-btn" @click="handleClose">
                <el-icon :size="18"><Close /></el-icon>
              </button>
            </div>
          </div>

          <!-- Main Content -->
          <div class="kg-modal-body">
            <div ref="canvasRef" class="kg-canvas" @click="deselectNode">
              <svg v-if="hasGraph" :viewBox="viewBoxStr" class="kg-svg"
                @wheel.prevent="handleWheel" @mousedown="startPan" @mousemove="onPan"
                @mouseup="endPan" @mouseleave="endPan">
                <defs>
                  <!-- Subtle dot grid -->
                  <pattern id="halftone" width="24" height="24" patternUnits="userSpaceOnUse">
                    <circle cx="12" cy="12" r="2.2" fill="#a5b4fc" opacity="0.15"/>
                  </pattern>
                  <pattern id="halftone2" width="48" height="48" patternUnits="userSpaceOnUse">
                    <circle cx="24" cy="24" r="4" fill="#c7d2fe" opacity="0.08"/>
                  </pattern>

                  <!-- Soft shadow -->
                  <filter id="popShadow" x="-20%" y="-20%" width="160%" height="160%">
                    <feDropShadow dx="3" dy="3" stdDeviation="2" flood-color="#6366f1" flood-opacity="0.2"/>
                  </filter>
                  <filter id="popShadowRoot" x="-20%" y="-20%" width="160%" height="160%">
                    <feDropShadow dx="4" dy="4" stdDeviation="3" flood-color="#4338ca" flood-opacity="0.25"/>
                  </filter>
                  <filter id="popShadowSelected" x="-20%" y="-20%" width="160%" height="160%">
                    <feDropShadow dx="6" dy="6" stdDeviation="0" flood-color="#6366f1" flood-opacity="0.6"/>
                  </filter>

                  <!-- Fills: distinct hues, soft saturation -->
                  <linearGradient id="rootFill" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#6366f1"/>
                    <stop offset="100%" stop-color="#4f46e5"/>
                  </linearGradient>
                  <linearGradient id="conceptFill" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#bae6fd"/>
                    <stop offset="100%" stop-color="#7dd3fc"/>
                  </linearGradient>
                  <linearGradient id="theoremFill" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#fda4af"/>
                    <stop offset="100%" stop-color="#fb7185"/>
                  </linearGradient>
                  <linearGradient id="methodFill" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#bbf7d0"/>
                    <stop offset="100%" stop-color="#86efac"/>
                  </linearGradient>

                  <!-- Arrow markers -->
                  <marker id="arrow-prerequisite" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M 0 1 L 11 6 L 0 11 z" fill="#fb7185" stroke="none"/>
                  </marker>
                  <marker id="arrow-derives" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M 0 1 L 11 6 L 0 11 z" fill="#6366f1" stroke="none"/>
                  </marker>
                  <marker id="arrow-applies" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M 0 1 L 11 6 L 0 11 z" fill="#38bdf8" stroke="none"/>
                  </marker>
                  <marker id="arrow-contrasts" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M 0 1 L 11 6 L 0 11 z" fill="#4ade80" stroke="none"/>
                  </marker>
                  <marker id="arrow-default" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M 0 1 L 11 6 L 0 11 z" fill="#94a3b8" stroke="none"/>
                  </marker>
                </defs>

                <!-- Pop-art background: off-white with halftone -->
                <rect :x="viewBox.x - 200" :y="viewBox.y - 200" :width="viewBox.width + 400" :height="viewBox.height + 400" fill="#fafaf0"/>
                <rect :x="viewBox.x - 200" :y="viewBox.y - 200" :width="viewBox.width + 400" :height="viewBox.height + 400" fill="url(#halftone)"/>
                <rect :x="viewBox.x - 200" :y="viewBox.y - 200" :width="viewBox.width + 400" :height="viewBox.height + 400" fill="url(#halftone2)"/>

                <!-- Edges Layer -->
                <g class="kg-edges-layer">
                  <g v-for="edge in graphData.edges" :key="edge.source + '-' + edge.target">
                    <!-- Glow layer -->
                    <path :d="getEdgePath(edge)" fill="none"
                      :style="getEdgeGlowStyle(edge)"/>
                    <!-- Main edge -->
                    <path :d="getEdgePath(edge)" fill="none"
                      :style="getEdgeMainStyle(edge)"
                      :marker-end="getArrowMarker(edge.relation)"/>
                    <text v-if="showEdgeLabels && getEdgeMidpoint(edge)"
                      :x="getEdgeMidpoint(edge)!.x" :y="getEdgeMidpoint(edge)!.y"
                      class="kg-edge-label">{{ getRelationLabel(edge.relation) }}</text>
                  </g>
                </g>

                <!-- Nodes Layer -->
                <g class="kg-nodes-layer">
                  <g v-for="node in graphData.nodes" :key="node.id"
                    class="kg-node-group"
                    :class="{
                      'kg-node-selected': selectedNode?.id === node.id,
                      'kg-node-highlighted': highlightedNodes.includes(node.id),
                      'kg-node-dimmed': dimmedNodes.includes(node.id),
                      'kg-node-dragging': draggingNode?.id === node.id,
                    }"
                    :transform="`translate(${node.x}, ${node.y})`"
                    @mousedown.stop="startNodeDrag(node, $event)"
                    @click.stop="if (!dragMoved) selectNode(node)"
                    @mouseenter="hoverNode(node)"
                    @mouseleave="unhoverNode">

                    <!-- Soft drop shadow -->
                    <rect
                      :x="-getNodeWidth(node)/2 + 1"
                      :y="-getNodeHeight(node)/2 + 2"
                      :width="getNodeWidth(node)"
                      :height="getNodeHeight(node)"
                      :rx="node.type === 'root' ? getNodeHeight(node)/2 : 10"
                      fill="rgba(99,102,241,0.18)"
                      :filter="node.type === 'root' ? 'url(#popShadowRoot)' : 'url(#popShadow)'"
                      style="pointer-events:none"/>

                    <!-- Node body -->
                    <rect
                      :x="-getNodeWidth(node)/2"
                      :y="-getNodeHeight(node)/2"
                      :width="getNodeWidth(node)"
                      :height="getNodeHeight(node)"
                      :rx="node.type === 'root' ? getNodeHeight(node)/2 : 10"
                      :style="getNodeStyle(node)"/>

                    <!-- Selection ring (thick pop border) -->
                    <rect v-if="selectedNode?.id === node.id"
                      :x="-getNodeWidth(node)/2 - 5"
                      :y="-getNodeHeight(node)/2 - 5"
                      :width="getNodeWidth(node) + 10"
                      :height="getNodeHeight(node) + 10"
                      :rx="node.type === 'root' ? getNodeHeight(node)/2 + 5 : 14"
                      fill="none" stroke="#6366f1" stroke-width="2.5"
                      stroke-dasharray="6 3"
                      class="kg-node-ring"/>

                    <!-- Label only (no icon, cleaner pop look) -->
                    <text x="0" y="1"
                      class="kg-node-label"
                      :style="{
                        fontSize: node.type === 'root' ? '14px' : '12px',
                        fontWeight: '900',
                        fill: getNodeTextColor(node),
                        letterSpacing: node.type === 'root' ? '0.5px' : '0px'
                      }">{{ node.label }}</text>
                  </g>
                </g>
              </svg>

              <!-- Empty State -->
              <div v-if="!hasGraph && !loading" class="kg-empty-state">
                <div class="kg-empty-illustration">
                  <div class="kg-empty-circle">
                    <el-icon :size="48"><Share /></el-icon>
                  </div>
                  <div class="kg-empty-dots"><span></span><span></span><span></span></div>
                </div>
                <h3 class="kg-empty-title">??Knowledge Graph</h3>
                <p class="kg-empty-desc">??Knowledge Graph????????relations</p>
                <button class="kg-btn kg-btn-primary kg-btn-large" @click="generateGraph">
                  <el-icon><MagicStick /></el-icon>Generate Now
                </button>
              </div>

              <!-- Loading State -->
              <div v-if="loading" class="kg-loading-state">
                <div class="kg-loading-spinner">
                  <div class="kg-spinner-ring"></div>
                  <div class="kg-spinner-ring"></div>
                  <div class="kg-spinner-ring"></div>
                </div>
                <p class="kg-loading-text">????Knowledge Graph...</p>
                <p class="kg-loading-hint">AI is analyzing course content and building concept relationships</p>
              </div>

              <!-- Node Detail Panel -->
              <Transition name="slide-right">
                <div v-if="selectedNode" class="kg-detail-panel">
                  <div class="kg-detail-header">
                    <div class="kg-detail-type" :style="{ background: getNodeAccent(selectedNode) + '20', color: getNodeAccent(selectedNode) }">
                      {{ getNodeIcon(selectedNode.type) }} {{ getTypeLabel(selectedNode.type) }}
                    </div>
                    <button class="kg-detail-close" @click="deselectNode"><el-icon><Close /></el-icon></button>
                  </div>
                  <h3 class="kg-detail-title">{{ selectedNode.label }}</h3>
                  <div v-if="selectedNode.description" class="kg-detail-section">
                    <h4 class="kg-detail-section-title">Description</h4>
                    <p class="kg-detail-description">{{ selectedNode.description }}</p>
                  </div>
                  <div v-if="relatedNodes.length > 0" class="kg-detail-section">
                    <h4 class="kg-detail-section-title">Related Concepts</h4>
                    <div class="kg-related-nodes">
                      <button v-for="rel in relatedNodes" :key="rel.node.id"
                        class="kg-related-node" @click="selectNode(rel.node)">
                        <span class="kg-related-icon" :style="{ background: getNodeAccent(rel.node) + '20' }">
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
                    <button v-if="selectedNode.chapter_id" class="kg-btn kg-btn-primary kg-btn-block"
                      @click="navigateToNode(selectedNode.chapter_id)">
                      <el-icon><Position /></el-icon>Go to Learn
                    </button>
                  </div>
                </div>
              </Transition>

              <!-- Minimap -->
              <Transition name="fade">
                <div v-if="showMinimap && hasGraph" class="kg-minimap">
                  <svg :viewBox="minimapViewBox" class="kg-minimap-svg">
                    <rect width="100%" height="100%" fill="#f8fafc"/>
                    <circle v-for="node in graphData.nodes" :key="'mini-' + node.id"
                      :cx="node.x" :cy="node.y" r="5"
                      :fill="getNodeAccent(node)" :opacity="selectedNode?.id === node.id ? 1 : 0.5"/>
                    <rect :x="viewBox.x" :y="viewBox.y" :width="viewBox.width" :height="viewBox.height"
                      fill="rgba(99,102,241,0.06)" stroke="#6366f1" stroke-width="3" rx="4"/>
                  </svg>
                </div>
              </Transition>
            </div>

            <!-- Legend -->
            <div v-if="hasGraph" class="kg-legend">
              <div class="kg-legend-header">
                <span class="kg-legend-title kg-legend-course-name" :title="courseStore.currentCourse?.course_name">{{ courseStore.currentCourse?.course_name || 'Legend' }}</span>
                <button class="kg-legend-toggle" @click="showEdgeLabels = !showEdgeLabels">
                  <el-icon :size="14"><View /></el-icon>
                  {{ showEdgeLabels ? 'Hide' : 'Show' }}relations
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
              <button class="kg-zoom-btn" @click="zoomIn" title="??"><el-icon><Plus /></el-icon></button>
              <div class="kg-zoom-level"><span>{{ Math.round(zoomLevel) }}%</span></div>
              <button class="kg-zoom-btn" @click="zoomOut" title="??"><el-icon><Minus /></el-icon></button>
              <div class="kg-zoom-divider"></div>
              <button class="kg-zoom-btn" @click="fitView" title="????"><el-icon><FullScreen /></el-icon></button>
            </div>
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
  Share, Search, Close, MagicStick, Refresh, Download, MapLocation,
  Compass, Position, Plus, Minus, FullScreen, ArrowRight, View
} from '@element-plus/icons-vue'
import http from '../utils/http'

const courseStore = useCourseStore()

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

const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0 })
const viewBoxStart = ref({ x: 0, y: 0 })

// Node dragging
const draggingNode = ref<any>(null)
const dragOffset = ref({ x: 0, y: 0 })
const dragMoved = ref(false)

const nodeTypes = [
  { value: 'root',    label: 'core-topic',   color: '#6366f1' },
  { value: 'concept', label: 'core-concept', color: '#38bdf8' },
  { value: 'theorem', label: 'key-theorem',  color: '#fb7185' },
  { value: 'method',  label: 'core-method',  color: '#4ade80' }
]

const relationTypes: Record<string, { label: string; color: string }> = {
  'prerequisite': { label: 'prerequisite', color: '#fb7185' },
  'derives':      { label: 'derives',      color: '#6366f1' },
  'applies_to':   { label: 'applies',      color: '#38bdf8' },
  'contrasts_with':{ label: 'contrast',    color: '#4ade80' },
  'extends':      { label: 'extends',      color: '#818cf8' },
  'implements':   { label: 'implements',   color: '#6366f1' },
  'leads_to':     { label: 'leads-to',     color: '#fb7185' }
}

const hasGraph = computed(() => graphData.value.nodes.length > 0)

const relatedNodes = computed(() => {
  if (!selectedNode.value) return []
  const related: { node: any; relation: string }[] = []
  const nodeId = selectedNode.value.id
  graphData.value.edges.forEach(edge => {
    if (edge.source === nodeId) {
      const t = graphData.value.nodes.find(n => n.id === edge.target)
      if (t) related.push({ node: t, relation: edge.relation })
    } else if (edge.target === nodeId) {
      const s = graphData.value.nodes.find(n => n.id === edge.source)
      if (s) related.push({ node: s, relation: edge.relation })
    }
  })
  return related.slice(0, 5)
})

const handleClose = () => { courseStore.showKnowledgeGraph = false }
const toggleMinimap = () => { showMinimap.value = !showMinimap.value }

const loadGraph = async () => {
  if (!courseStore.currentCourseId) return
  try {
    const res = await http.get(`/api/courses/${courseStore.currentCourseId}/knowledge_graph`)
    const data = res.data
    if (data.status === 'success' && data.data.nodes?.length > 0) {
      graphData.value = data.data
      layoutGraph()
    }
  } catch (e) { console.error('Failed to load graph:', e) }
}

const generateGraph = async () => {
  if (!courseStore.currentCourseId) { ElMessage.warning('Please select a course first'); return }
  loading.value = true
  try {
    const res = await http.post(`/api/courses/${courseStore.currentCourseId}/knowledge_graph`)
    const data = res.data
    if (data.status === 'success') {
      graphData.value = data.data
      layoutGraph()
      ElMessage.success('Knowledge Graph????')
    } else {
      ElMessage.error('Generation failed: ' + (data.message || 'Unknown error'))
    }
  } catch (e: any) {
    ElMessage.error('Generation failed: ' + (e.message || 'Network error'))
  } finally {
    loading.value = false
  }
}

const layoutGraph = () => {
  const nodes = graphData.value.nodes
  const edges = graphData.value.edges
  if (!nodes.length) return

  const CENTER_X = 700, CENTER_Y = 450
  const children: Record<string, string[]> = {}
  nodes.forEach(n => { children[n.id] = [] })
  edges.forEach(e => { if (children[e.source]) children[e.source].push(e.target) })

  const root = nodes.find(n => n.type === 'root') || nodes[0]
  if (!root) return
  root.x = CENTER_X; root.y = CENTER_Y

  const mainBranches = children[root.id] || []
  const angleStep = (2 * Math.PI) / Math.max(mainBranches.length, 1)

  mainBranches.forEach((nodeId, index) => {
    const node = nodes.find(n => n.id === nodeId)
    if (!node) return
    const angle = -Math.PI / 2 + index * angleStep
    node.x = CENTER_X + Math.cos(angle) * 380
    node.y = CENTER_Y + Math.sin(angle) * 380

    const subBranches = children[nodeId] || []
    const spread = angleStep * 0.72
    subBranches.forEach((subId, si) => {
      const sub = nodes.find(n => n.id === subId)
      if (!sub) return
      const subAngle = angle - spread / 2 + (si + 0.5) * (spread / Math.max(subBranches.length, 1))
      sub.x = node.x + Math.cos(subAngle) * 260
      sub.y = node.y + Math.sin(subAngle) * 260

      const leaves = children[subId] || []
      leaves.forEach((leafId, li) => {
        const leaf = nodes.find(n => n.id === leafId)
        if (!leaf) return
        const leafAngle = subAngle + (li - (leaves.length - 1) / 2) * 0.4
        leaf.x = sub.x + Math.cos(leafAngle) * 200
        leaf.y = sub.y + Math.sin(leafAngle) * 200
      })
    })
  })

  nodes.forEach(n => { if (n.x === undefined) { n.x = CENTER_X + Math.random() * 400 - 200; n.y = CENTER_Y + Math.random() * 400 - 200 } })
  applyGentleForce()
  fitView()
}

const applyGentleForce = () => {
  const nodes = graphData.value.nodes
  for (let i = 0; i < 50; i++) {
    for (let j = 0; j < nodes.length; j++) {
      for (let k = j + 1; k < nodes.length; k++) {
        const dx = nodes[k].x - nodes[j].x
        const dy = nodes[k].y - nodes[j].y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        if (dist < 160) {
          const f = (160 - dist) * 0.12
          nodes[j].x -= (dx / dist) * f; nodes[j].y -= (dy / dist) * f
          nodes[k].x += (dx / dist) * f; nodes[k].y += (dy / dist) * f
        }
      }
    }
  }
}

const fitView = () => {
  const nodes = graphData.value.nodes
  if (!nodes.length) return
  const pad = 120
  const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y)
  viewBox.value = {
    x: Math.min(...xs) - pad,
    y: Math.min(...ys) - pad,
    width: Math.max(Math.max(...xs) - Math.min(...xs) + pad * 2, 800),
    height: Math.max(Math.max(...ys) - Math.min(...ys) + pad * 2, 600)
  }
}

// Node helpers
const getNodeWidth = (node: any) => {
  const charW = node.type === 'root' ? 15 : 13
  const base = node.type === 'root' ? 160 : 120
  return Math.max(base, (node.label?.length || 0) * charW + 56)
}
const getNodeHeight = (node: any) => node.type === 'root' ? 56 : 46
const getNodeIcon = (type: string) => ''
const getNodeAccent = (node: any) => nodeTypes.find(t => t.value === node.type)?.color || '#ffffff'
const getTypeLabel = (type: string) => nodeTypes.find(t => t.value === type)?.label || type
const getRelationLabel = (relation: string) => relationTypes[relation]?.label || relation

const getNodeTextColor = (node: any) => {
  // root (indigo) and theorem (rose) are dark fills → white text
  // concept (sky) and method (green) are light fills → dark text
  if (node.type === 'root')    return '#fff'
  if (node.type === 'concept') return '#0c4a6e'
  if (node.type === 'theorem') return '#fff'
  if (node.type === 'method')  return '#14532d'
  return '#1e293b'
}

const getNodeStyle = (node: any) => {
  const fillMap: Record<string, string> = {
    root:    'url(#rootFill)',
    concept: 'url(#conceptFill)',
    theorem: 'url(#theoremFill)',
    method:  'url(#methodFill)'
  }
  const strokeMap: Record<string, string> = {
    root:    '#4338ca',
    concept: '#7dd3fc',
    theorem: '#f43f5e',
    method:  '#86efac'
  }
  return {
    fill: fillMap[node.type] || '#e0e7ff',
    stroke: strokeMap[node.type] || '#a5b4fc',
    strokeWidth: node.type === 'root' ? '2' : '1.5',
  }
}

// Edge helpers
const getEdgePath = (edge: any) => {
  const s = graphData.value.nodes.find(n => n.id === edge.source)
  const t = graphData.value.nodes.find(n => n.id === edge.target)
  if (!s || !t) return ''
  const dx = t.x - s.x, dy = t.y - s.y
  const cx = (s.x + t.x) / 2 - dy * 0.15
  const cy = (s.y + t.y) / 2 + dx * 0.15
  return `M ${s.x} ${s.y} Q ${cx} ${cy} ${t.x} ${t.y}`
}

const getEdgeMidpoint = (edge: any) => {
  const s = graphData.value.nodes.find(n => n.id === edge.source)
  const t = graphData.value.nodes.find(n => n.id === edge.target)
  if (!s || !t) return null
  return { x: (s.x + t.x) / 2, y: (s.y + t.y) / 2 - 10 }
}

const getEdgeColor = (edge: any) => relationTypes[edge.relation]?.color || '#475569'

const getEdgeGlowStyle = (edge: any) => {
  // No glow in pop-art style, return invisible
  return { stroke: 'none', strokeWidth: '0' }
}

const getEdgeMainStyle = (edge: any) => {
  const color = getEdgeColor(edge)
  const isActive = selectedNode.value && (edge.source === selectedNode.value.id || edge.target === selectedNode.value.id)
  const isDimmed = selectedNode.value && !isActive
  return {
    stroke: isDimmed ? '#e2e8f0' : isActive ? color : '#c7d2fe',
    strokeWidth: isActive ? '2' : '1.5',
    opacity: isDimmed ? '0.3' : '1',
    strokeDasharray: isActive ? 'none' : '6 4',
  }
}

const getArrowMarker = (relation: string) => {
  if (relation === 'prerequisite') return 'url(#arrow-prerequisite)'
  if (relation === 'derives') return 'url(#arrow-derives)'
  if (relation === 'applies_to') return 'url(#arrow-applies)'
  if (relation === 'contrasts_with') return 'url(#arrow-contrasts)'
  return 'url(#arrow-default)'
}

const selectNode = (node: any) => { selectedNode.value = node }
const deselectNode = () => { selectedNode.value = null }
const hoverNode = (node: any) => { hoveredNodeId.value = node.id }
const unhoverNode = () => { hoveredNodeId.value = null }

// Convert screen coords to SVG viewBox coords
const screenToSvg = (clientX: number, clientY: number) => {
  if (!canvasRef.value) return { x: 0, y: 0 }
  const rect = canvasRef.value.getBoundingClientRect()
  return {
    x: viewBox.value.x + (clientX - rect.left) * viewBox.value.width / rect.width,
    y: viewBox.value.y + (clientY - rect.top) * viewBox.value.height / rect.height
  }
}

const startNodeDrag = (node: any, e: MouseEvent) => {
  e.stopPropagation()
  draggingNode.value = node
  dragMoved.value = false
  const svgPos = screenToSvg(e.clientX, e.clientY)
  dragOffset.value = { x: svgPos.x - node.x, y: svgPos.y - node.y }
}

const navigateToNode = (nodeId: string) => {
  courseStore.scrollToNode(nodeId)
  handleClose()
  ElMessage.success('Navigated to chapter')
}

const handleSearchInput = () => {
  if (!searchQuery.value.trim()) { highlightedNodes.value = []; dimmedNodes.value = []; return }
  const q = searchQuery.value.toLowerCase()
  highlightedNodes.value = graphData.value.nodes.filter(n => n.label?.toLowerCase().includes(q)).map(n => n.id)
  dimmedNodes.value = graphData.value.nodes.filter(n => !n.label?.toLowerCase().includes(q)).map(n => n.id)
}

const handleSearch = () => {
  if (!searchQuery.value.trim()) return
  const q = searchQuery.value.toLowerCase()
  const found = graphData.value.nodes.find(n => n.label?.toLowerCase().includes(q) || n.description?.toLowerCase().includes(q))
  if (found) {
    selectNode(found)
    viewBox.value = { x: found.x - 200, y: found.y - 150, width: 400, height: 300 }
  } else { ElMessage.info('No matching nodes found') }
}

const clearSearch = () => { searchQuery.value = ''; highlightedNodes.value = []; dimmedNodes.value = [] }

const zoomIn = () => {
  const cx = viewBox.value.x + viewBox.value.width / 2, cy = viewBox.value.y + viewBox.value.height / 2
  viewBox.value.width *= 0.8; viewBox.value.height *= 0.8
  viewBox.value.x = cx - viewBox.value.width / 2; viewBox.value.y = cy - viewBox.value.height / 2
}
const zoomOut = () => {
  const cx = viewBox.value.x + viewBox.value.width / 2, cy = viewBox.value.y + viewBox.value.height / 2
  viewBox.value.width *= 1.25; viewBox.value.height *= 1.25
  viewBox.value.x = cx - viewBox.value.width / 2; viewBox.value.y = cy - viewBox.value.height / 2
}
const resetView = () => fitView()

const handleWheel = (e: WheelEvent) => {
  const scale = e.deltaY > 0 ? 1.1 : 0.9
  viewBox.value.width *= scale; viewBox.value.height *= scale
}

const startPan = (e: MouseEvent) => {
  if ((e.target as Element)?.tagName !== 'svg' && (e.target as Element)?.tagName !== 'rect') return
  isPanning.value = true
  panStart.value = { x: e.clientX, y: e.clientY }
  viewBoxStart.value = { x: viewBox.value.x, y: viewBox.value.y }
}

const onPan = (e: MouseEvent) => {
  if (draggingNode.value) {
    const svgPos = screenToSvg(e.clientX, e.clientY)
    draggingNode.value.x = svgPos.x - dragOffset.value.x
    draggingNode.value.y = svgPos.y - dragOffset.value.y
    dragMoved.value = true
    return
  }
  if (!isPanning.value || !canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  const dx = (e.clientX - panStart.value.x) * viewBox.value.width / rect.width
  const dy = (e.clientY - panStart.value.y) * viewBox.value.height / rect.height
  viewBox.value.x = viewBoxStart.value.x - dx
  viewBox.value.y = viewBoxStart.value.y - dy
}

const endPan = () => {
  draggingNode.value = null
  isPanning.value = false
}

const downloadImage = () => {
  if (!canvasRef.value) return
  const svg = canvasRef.value.querySelector('svg')
  if (!svg) return
  const serializer = new XMLSerializer()
  let source = serializer.serializeToString(svg)
  if (!source.includes('xmlns="http://www.w3.org/2000/svg"'))
    source = source.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"')
  const blob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = `knowledge-graph-${courseStore.currentCourseId}.svg`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 100)
  ElMessage.success('SVG exported')
}

const handleKeydown = (e: KeyboardEvent) => {
  if (!courseStore.showKnowledgeGraph) return
  if (e.key === 'Escape') {
    if (selectedNode.value) deselectNode()
    else handleClose()
  } else if (e.key === 'f' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault()
    ;(document.querySelector('.kg-search-input') as HTMLInputElement)?.focus()
  }
}

watch(() => courseStore.showKnowledgeGraph, (show) => {
  if (show) { loadGraph(); document.addEventListener('keydown', handleKeydown) }
  else { document.removeEventListener('keydown', handleKeydown); selectedNode.value = null; searchQuery.value = '' }
})

watch(() => courseStore.currentCourseId, () => {
  if (courseStore.showKnowledgeGraph) loadGraph()
})
</script>

<style scoped>
/* ===== GLASSMORPHISM THEME (matches app UI) ===== */
.kg-modal-overlay {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; padding: 32px;
}

.kg-modal-container {
  width: 100%; height: 100%; max-width: 1400px; max-height: 900px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 25px 60px rgba(0,0,0,0.15), 0 0 0 1px rgba(0,0,0,0.03);
  display: flex; flex-direction: column; overflow: hidden;
  animation: modalIn 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes modalIn {
  from { opacity: 0; transform: scale(0.95) translateY(20px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}

.kg-modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px;
  background: rgba(255, 255, 255, 0.7);
  border-bottom: 1px solid rgba(226, 232, 240, 0.8);
  gap: 20px; flex-shrink: 0;
}

.kg-header-left { display: flex; align-items: center; }
.kg-title-wrapper { display: flex; align-items: center; gap: 12px; }

.kg-title-icon {
  width: 36px; height: 36px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center; color: #fff;
  box-shadow: 0 4px 12px rgba(99,102,241,0.35);
}

.kg-title { font-size: 15px; font-weight: 700; color: #1e293b; margin: 0; letter-spacing: -0.2px; }
.kg-subtitle { font-size: 11px; color: #94a3b8; margin: 2px 0 0 0; font-weight: 500; }

.kg-header-center { flex: 1; max-width: 380px; }
.kg-search-wrapper { position: relative; display: flex; align-items: center; }
.kg-search-icon { position: absolute; left: 11px; color: #94a3b8; }

.kg-search-input {
  width: 100%; padding: 8px 36px;
  border: 1px solid rgba(226,232,240,0.8); border-radius: 12px;
  font-size: 13px; font-weight: 500;
  background: rgba(255,255,255,0.6); color: #1e293b;
  backdrop-filter: blur(8px);
  transition: all 0.2s;
}
.kg-search-input::placeholder { color: #94a3b8; }
.kg-search-input:focus {
  outline: none; border-color: rgba(99,102,241,0.5);
  background: rgba(255,255,255,0.9);
  box-shadow: 0 0 0 3px rgba(99,102,241,0.1);
}

.kg-search-clear {
  position: absolute; right: 8px; background: none; border: none;
  color: #94a3b8; cursor: pointer; padding: 4px; display: flex;
  border-radius: 6px; transition: all 0.2s;
}
.kg-search-clear:hover { background: rgba(0,0,0,0.05); color: #64748b; }

.kg-header-right { display: flex; align-items: center; gap: 6px; }

.kg-action-btn {
  width: 36px; height: 36px; border-radius: 10px;
  border: 1px solid rgba(226,232,240,0.6);
  background: rgba(255,255,255,0.5);
  color: #64748b; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.kg-action-btn:hover { background: rgba(255,255,255,0.9); color: #4f46e5; border-color: rgba(99,102,241,0.3); transform: translateY(-1px); box-shadow: 0 4px 10px rgba(0,0,0,0.08); }
.kg-action-btn.active { background: rgba(99,102,241,0.1); color: #4f46e5; border-color: rgba(99,102,241,0.3); }

.kg-btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 8px 16px; border-radius: 10px; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all 0.2s; border: none;
}
.kg-btn-primary {
  background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff;
  box-shadow: 0 4px 14px rgba(99,102,241,0.35);
}
.kg-btn-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(99,102,241,0.45); }
.kg-btn-secondary {
  background: rgba(255,255,255,0.6); color: #475569;
  border: 1px solid rgba(226,232,240,0.8);
}
.kg-btn-secondary:hover:not(:disabled) { background: rgba(255,255,255,0.9); color: #1e293b; transform: translateY(-1px); box-shadow: 0 4px 10px rgba(0,0,0,0.08); }
.kg-btn-large { padding: 11px 22px; font-size: 14px; border-radius: 12px; }
.kg-btn-block { width: 100%; justify-content: center; }
.kg-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.kg-close-btn {
  width: 36px; height: 36px; border-radius: 10px;
  border: 1px solid rgba(226,232,240,0.6);
  background: rgba(255,255,255,0.5);
  color: #64748b; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s; margin-left: 4px;
}
.kg-close-btn:hover { background: rgba(239,68,68,0.08); color: #ef4444; border-color: rgba(239,68,68,0.2); }

.kg-modal-body { flex: 1; position: relative; overflow: hidden; }

.kg-canvas { width: 100%; height: 100%; position: relative; cursor: grab; background: #fafaf0; }
.kg-canvas:active { cursor: grabbing; }
.kg-svg { width: 100%; height: 100%; }

.kg-edge-label {
  font-size: 10px; fill: #334155; text-anchor: middle; pointer-events: none;
  font-weight: 600; letter-spacing: 0.2px;
}

.kg-node-group { cursor: pointer; transition: opacity 0.2s; }
.kg-node-group:hover rect { filter: brightness(1.08); }
.kg-node-dragging { cursor: grabbing; }
.kg-node-dimmed { opacity: 0.2; }

.kg-node-ring { pointer-events: none; animation: pulseRing 2s ease-in-out infinite; }
@keyframes pulseRing {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

.kg-node-icon { text-anchor: middle; dominant-baseline: middle; pointer-events: none; }
.kg-node-label {
  font-weight: 900;
  font-family: system-ui, -apple-system, sans-serif;
  pointer-events: none; dominant-baseline: middle; text-anchor: middle;
}

/* Empty State */
.kg-empty-state {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 20px;
  background: rgba(255,255,255,0.5);
}
.kg-empty-illustration { position: relative; }
.kg-empty-circle {
  width: 100px; height: 100px;
  background: linear-gradient(135deg, rgba(99,102,241,0.1), rgba(139,92,246,0.1));
  border: 1px solid rgba(99,102,241,0.2);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center; color: #6366f1;
  box-shadow: 0 0 40px rgba(99,102,241,0.12);
}
.kg-empty-dots { position: absolute; bottom: -18px; left: 50%; transform: translateX(-50%); display: flex; gap: 6px; }
.kg-empty-dots span { width: 7px; height: 7px; background: #c7d2fe; border-radius: 50%; animation: bounce 1.4s ease-in-out infinite; }
.kg-empty-dots span:nth-child(2) { animation-delay: 0.2s; background: #a5b4fc; }
.kg-empty-dots span:nth-child(3) { animation-delay: 0.4s; background: #818cf8; }
@keyframes bounce { 0%,80%,100% { transform: translateY(0); } 40% { transform: translateY(-7px); } }
.kg-empty-title { font-size: 18px; font-weight: 700; color: #1e293b; margin: 0; }
.kg-empty-desc { font-size: 13px; color: #64748b; margin: 0; }

/* Loading */
.kg-loading-state {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 18px;
  background: rgba(255,255,255,0.85); backdrop-filter: blur(8px);
}
.kg-loading-spinner { position: relative; width: 52px; height: 52px; }
.kg-spinner-ring {
  position: absolute; inset: 0;
  border: 2.5px solid rgba(99,102,241,0.1); border-top-color: #6366f1;
  border-radius: 50%; animation: spin 1s linear infinite;
}
.kg-spinner-ring:nth-child(2) { inset: 8px; border-top-color: #8b5cf6; animation-duration: 1.5s; animation-direction: reverse; }
.kg-spinner-ring:nth-child(3) { inset: 16px; border-top-color: #a78bfa; animation-duration: 2s; }
@keyframes spin { to { transform: rotate(360deg); } }
.kg-loading-text { font-size: 14px; font-weight: 600; color: #1e293b; margin: 0; }
.kg-loading-hint { font-size: 12px; color: #64748b; margin: 0; }

/* Detail Panel */
.kg-detail-panel {
  position: absolute; top: 16px; right: 16px; width: 300px;
  background: rgba(255,255,255,0.92);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,0.6);
  border-radius: 18px;
  box-shadow: 0 20px 50px rgba(0,0,0,0.1), 0 0 0 1px rgba(0,0,0,0.03);
  overflow: hidden; z-index: 10;
}
.kg-detail-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 14px;
  border-bottom: 1px solid rgba(226,232,240,0.6);
  background: rgba(248,250,252,0.8);
}
.kg-detail-type {
  font-size: 11px; font-weight: 700; padding: 3px 9px;
  border-radius: 20px; letter-spacing: 0.3px;
}
.kg-detail-close {
  width: 28px; height: 28px; border-radius: 8px;
  border: 1px solid rgba(226,232,240,0.6);
  background: rgba(255,255,255,0.7); color: #64748b; cursor: pointer;
  display: flex; align-items: center; justify-content: center; transition: all 0.2s;
}
.kg-detail-close:hover { background: rgba(239,68,68,0.08); color: #ef4444; border-color: rgba(239,68,68,0.2); }
.kg-detail-title { font-size: 15px; font-weight: 700; color: #0f172a; margin: 0; padding: 12px 14px 0; }
.kg-detail-section { padding: 10px 14px; }
.kg-detail-section-title {
  font-size: 10px; font-weight: 700; color: #94a3b8;
  text-transform: uppercase; letter-spacing: 0.8px; margin: 0 0 7px 0;
}
.kg-detail-description {
  font-size: 12px; color: #475569; line-height: 1.65; margin: 0;
  background: rgba(248,250,252,0.8); padding: 10px 12px; border-radius: 10px;
  border: 1px solid rgba(226,232,240,0.5);
}
.kg-related-nodes { display: flex; flex-direction: column; gap: 5px; }
.kg-related-node {
  display: flex; align-items: center; gap: 9px; padding: 8px 10px;
  background: rgba(248,250,252,0.7); border: 1px solid rgba(226,232,240,0.5);
  border-radius: 10px; cursor: pointer; transition: all 0.2s; width: 100%; text-align: left;
}
.kg-related-node:hover { background: rgba(99,102,241,0.06); border-color: rgba(99,102,241,0.2); transform: translateX(3px); }
.kg-related-icon { width: 26px; height: 26px; border-radius: 7px; display: flex; align-items: center; justify-content: center; font-size: 12px; background: rgba(99,102,241,0.08); }
.kg-related-info { flex: 1; display: flex; flex-direction: column; gap: 1px; }
.kg-related-label { font-size: 12px; font-weight: 600; color: #334155; }
.kg-related-relation { font-size: 10px; color: #94a3b8; }
.kg-related-arrow { color: #cbd5e1; }
.kg-detail-actions {
  padding: 12px 14px;
  border-top: 1px solid rgba(226,232,240,0.6);
  background: rgba(248,250,252,0.6);
}

/* Minimap */
.kg-minimap {
  position: absolute; bottom: 16px; left: 16px; width: 160px; height: 100px;
  background: rgba(255,255,255,0.88);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.6);
  border-radius: 14px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.08);
  overflow: hidden; z-index: 10;
}
.kg-minimap-svg { width: 100%; height: 100%; }

/* Legend */
.kg-legend {
  position: absolute; bottom: 16px; left: 194px;
  background: rgba(255,255,255,0.88);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.6);
  border-radius: 14px; padding: 10px 14px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.08); z-index: 10;
}
.kg-legend-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 12px; }
.kg-legend-title { font-size: 10px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.8px; }
.kg-legend-course-name { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; vertical-align: middle; }
.kg-legend-toggle {
  display: flex; align-items: center; gap: 4px;
  background: rgba(99,102,241,0.08); border: 1px solid rgba(99,102,241,0.2);
  border-radius: 6px;
  font-size: 10px; font-weight: 600; color: #6366f1; cursor: pointer; padding: 3px 7px; transition: all 0.2s;
}
.kg-legend-toggle:hover { background: rgba(99,102,241,0.15); }
.kg-legend-items { display: flex; flex-wrap: wrap; gap: 8px; }
.kg-legend-item { display: flex; align-items: center; gap: 5px; }
.kg-legend-dot { width: 10px; height: 10px; border-radius: 3px; border: 2px solid rgba(0,0,0,0.15); }
.kg-legend-label { font-size: 11px; color: #475569; font-weight: 500; }

/* Zoom Controls */
.kg-zoom-controls {
  position: absolute; bottom: 16px; right: 16px;
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  background: rgba(255,255,255,0.88);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.6);
  padding: 5px; border-radius: 14px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.08); z-index: 10;
}
.kg-zoom-btn {
  width: 32px; height: 32px; border-radius: 9px;
  border: 1px solid rgba(226,232,240,0.5);
  background: transparent; color: #64748b; cursor: pointer;
  display: flex; align-items: center; justify-content: center; transition: all 0.2s;
}
.kg-zoom-btn:hover { background: rgba(99,102,241,0.08); color: #4f46e5; border-color: rgba(99,102,241,0.2); }
.kg-zoom-level { font-size: 10px; font-weight: 600; color: #64748b; padding: 2px 0; }
.kg-zoom-divider { width: 16px; height: 1px; background: rgba(226,232,240,0.8); margin: 2px 0; }

/* Transitions */
.modal-enter-active, .modal-leave-active { transition: all 0.3s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-from .kg-modal-container, .modal-leave-to .kg-modal-container { transform: scale(0.96) translateY(16px); }

.slide-right-enter-active, .slide-right-leave-active { transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.slide-right-enter-from, .slide-right-leave-to { opacity: 0; transform: translateX(16px); }

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

@media (max-width: 1024px) {
  .kg-modal-overlay { padding: 20px; }
  .kg-modal-container { max-height: none; }
  .kg-header-center { display: none; }
  .kg-detail-panel { width: 270px; }
  .kg-minimap { display: none; }
  .kg-legend { left: 16px; bottom: 72px; }
}

@media (max-width: 640px) {
  .kg-modal-overlay { padding: 0; }
  .kg-modal-container { border-radius: 0; }
  .kg-modal-header { padding: 10px 12px; flex-wrap: wrap; }
  .kg-header-left { order: 1; }
  .kg-header-right { order: 2; margin-left: auto; }
  .kg-detail-panel {
    position: fixed; inset: auto; bottom: 0; left: 0; right: 0; width: 100%;
    border-radius: 18px 18px 0 0; max-height: 60vh; overflow-y: auto;
  }
  .kg-legend { display: none; }
  .kg-zoom-controls { bottom: 76px; }
}
</style>

