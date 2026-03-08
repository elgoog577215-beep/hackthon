<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="courseStore.showKnowledgeGraph" class="kg-overlay" @click.self="handleClose">
        <div class="kg-container">
          <div class="kg-header">
            <div class="kg-header-left">
              <div class="kg-icon-wrap"><el-icon :size="16"><Share /></el-icon></div>
              <span class="kg-title">知识图谱</span>
            </div>
            <div class="kg-header-center" v-if="hasGraph">
              <div class="kg-search-wrap">
                <el-icon class="kg-search-ico"><Search /></el-icon>
                <input v-model="searchQuery" placeholder="搜索概念..." class="kg-search-input"
                  @input="handleSearchInput" @keyup.enter="handleSearch"/>
                <button v-if="searchQuery" class="kg-search-clear" @click="clearSearch">
                  <el-icon><Close /></el-icon>
                </button>
              </div>
            </div>
            <div class="kg-header-right">
              <template v-if="hasGraph">
                <button class="kg-hbtn" @click="generateGraph" :disabled="loading">
                  <el-icon :class="{'is-loading':loading}"><Refresh /></el-icon> 重新生成
                </button>
                <button class="kg-hbtn" @click="resetView">
                  <el-icon><FullScreen /></el-icon> 重置视图
                </button>
                <button class="kg-hbtn" @click="downloadImage">
                  <el-icon><Download /></el-icon> 导出
                </button>
              </template>
              <button v-if="!hasGraph" class="kg-btn-primary" :disabled="loading" @click="generateGraph">
                <el-icon :class="{'is-loading':loading}"><MagicStick /></el-icon>
                {{ loading ? '生成中...' : '生成图谱' }}
              </button>
              <button class="kg-close" @click="handleClose"><el-icon :size="16"><Close /></el-icon></button>
            </div>
          </div>
          <div class="kg-body">
            <div ref="canvasRef" class="kg-canvas" @click="deselectNode">
              <svg v-if="hasGraph" :viewBox="viewBoxStr" class="kg-svg"
                @wheel.prevent="handleWheel"
                @mousedown="startPan" @mousemove="onPan"
                @mouseup="endPan" @mouseleave="endPan">
                <defs>
                  <pattern id="kg-grid" width="40" height="40" patternUnits="userSpaceOnUse">
                    <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#e2e8f0" stroke-width="0.6"/>
                  </pattern>
                  <filter id="sf" x="-20%" y="-20%" width="140%" height="160%">
                    <feDropShadow dx="0" dy="2" stdDeviation="5" flood-color="#0f172a" flood-opacity="0.07"/>
                  </filter>
                  <filter id="sf-sel" x="-20%" y="-20%" width="140%" height="160%">
                    <feDropShadow dx="0" dy="4" stdDeviation="10" flood-color="#6366f1" flood-opacity="0.22"/>
                  </filter>
                  <clipPath id="clip-node">
                    <rect :x="-NODE_W/2" :y="-NODE_H/2" :width="NODE_W" :height="NODE_H" rx="8"/>
                  </clipPath>
                  <marker v-for="nt in nodeTypes" :key="'m-'+nt.value"
                    :id="'arr-'+nt.value" viewBox="0 0 10 10" refX="9" refY="5"
                    markerWidth="5" markerHeight="5" orient="auto">
                    <path d="M 0 1 L 9 5 L 0 9 z" :fill="nt.color"/>
                  </marker>
                  <marker id="arr-default" viewBox="0 0 10 10" refX="9" refY="5"
                    markerWidth="5" markerHeight="5" orient="auto">
                    <path d="M 0 1 L 9 5 L 0 9 z" fill="#94a3b8"/>
                  </marker>
                </defs>
                <rect :x="viewBox.x-600" :y="viewBox.y-600" :width="viewBox.width+1200" :height="viewBox.height+1200" fill="white"/>
                <rect :x="viewBox.x-600" :y="viewBox.y-600" :width="viewBox.width+1200" :height="viewBox.height+1200" fill="url(#kg-grid)"/>
                <g>
                  <g v-for="edge in graphData.edges" :key="edge.source+'-'+edge.target">
                    <path :d="getEdgePath(edge)" fill="none" :style="getEdgeStyle(edge)"/>
                    <text v-if="showEdgeLabels && getEdgeMid(edge)"
                      :x="getEdgeMid(edge)!.x" :y="getEdgeMid(edge)!.y - 6"
                      class="kg-elabel">{{ getRelLabel(edge.relation) }}</text>
                  </g>
                </g>
                <g>
                  <g v-for="node in graphData.nodes" :key="node.id"
                    :class="['kg-node', {'kg-node--sel': selectedNode && selectedNode.id===node.id, 'kg-node--dim': dimmedNodes.includes(node.id), 'kg-node--hi': highlightedNodes.includes(node.id)}]"
                    :transform="`translate(${node.x},${node.y})`"
                    @mousedown.stop="startNodeDrag(node,$event)"
                    @click.stop="!dragMoved && selectNode(node)">
                    <rect :x="-NODE_W/2" :y="-NODE_H/2" :width="NODE_W" :height="NODE_H" rx="8"
                      fill="white"
                      :stroke="selectedNode && selectedNode.id===node.id ? getAccent(node) : '#e2e8f0'"
                      :stroke-width="selectedNode && selectedNode.id===node.id ? 2 : 1"
                      :filter="selectedNode && selectedNode.id===node.id ? 'url(#sf-sel)' : 'url(#sf)'"/>
                    <g clip-path="url(#clip-node)">
                      <rect :x="-NODE_W/2" :y="-NODE_H/2" width="5" :height="NODE_H" :fill="getAccent(node)"/>
                    </g>
                    <text :x="-NODE_W/2+16" y="1" class="kg-nlabel"
                      :style="{fill: node.type==='root' ? '#0f172a' : '#334155', fontWeight: node.type==='root' ? '700' : '600'}">
                      {{ node.label }}
                    </text>
                  </g>
                </g>
              </svg>
              <div v-if="!hasGraph && !loading" class="kg-empty">
                <div class="kg-empty-icon"><el-icon :size="36"><Share /></el-icon></div>
                <p class="kg-empty-title">生成知识图谱</p>
                <p class="kg-empty-sub">AI 分析课程内容，构建概念关系网络</p>
                <button class="kg-btn-primary kg-btn-lg" @click="generateGraph">
                  <el-icon><MagicStick /></el-icon> 立即生成
                </button>
              </div>
              <div v-if="loading" class="kg-loading">
                <div class="kg-spin"><div/><div/><div/></div>
                <p class="kg-loading-t">正在生成知识图谱...</p>
                <p class="kg-loading-s">AI 正在分析课程内容，构建概念关系</p>
              </div>
              <div v-if="hasGraph" class="kg-legend">
                <div class="kg-legend-title">图例</div>
                <div class="kg-legend-items">
                  <div v-for="t in nodeTypes" :key="t.value" class="kg-legend-item">
                    <span class="kg-legend-bar" :style="{background:t.color}"/>
                    <span class="kg-legend-label">{{ t.label }}</span>
                  </div>
                </div>
                <button class="kg-legend-toggle" @click="showEdgeLabels=!showEdgeLabels">
                  {{ showEdgeLabels ? '隐藏' : '显示' }}关系标签
                </button>
              </div>
              <div v-if="hasGraph" class="kg-zoom">
                <button class="kg-zbtn" @click="zoomIn"><el-icon><Plus /></el-icon></button>
                <span class="kg-zlevel">{{ Math.round(zoomLevel) }}%</span>
                <button class="kg-zbtn" @click="zoomOut"><el-icon><Minus /></el-icon></button>
              </div>
              <div v-if="hasGraph" class="kg-stats">
                {{ graphData.nodes.length }} 个节点  {{ graphData.edges.length }} 条关系
              </div>
              <Transition name="slide-in">
                <div v-if="selectedNode" class="kg-detail" @click.stop>
                  <div class="kg-detail-head">
                    <span class="kg-detail-badge" :style="{background:getAccent(selectedNode)+'18', color:getAccent(selectedNode)}">
                      {{ getTypeLabel(selectedNode.type) }}
                    </span>
                    <button class="kg-detail-close" @click.stop="deselectNode"><el-icon><Close /></el-icon></button>
                  </div>
                  <h3 class="kg-detail-title">{{ selectedNode.label }}</h3>
                  <p v-if="selectedNode.description" class="kg-detail-desc">{{ selectedNode.description }}</p>
                  <div v-if="relatedNodes.length" class="kg-detail-related">
                    <div class="kg-detail-sec">相关概念</div>
                    <button v-for="r in relatedNodes" :key="r.node.id" class="kg-rel-item" @click.stop="selectNode(r.node)">
                      <span class="kg-rel-dot" :style="{background:getAccent(r.node)}"/>
                      <span class="kg-rel-name">{{ r.node.label }}</span>
                      <span class="kg-rel-tag">{{ getRelLabel(r.relation) }}</span>
                    </button>
                  </div>
                  <!-- 相关笔记与错题 -->
                  <div v-if="nodeNotes.length || nodeWrongAnswers.length" class="kg-detail-extra">
                    <div v-if="nodeNotes.length" class="kg-detail-section">
                      <button class="kg-sec-toggle" @click.stop="showNotesSection = !showNotesSection">
                        <span class="kg-sec-icon">📝</span>
                        <span class="kg-sec-label">相关笔记</span>
                        <span class="kg-sec-count">{{ nodeNotes.length }}</span>
                        <span class="kg-sec-arrow" :class="{ 'kg-sec-arrow--open': showNotesSection }">›</span>
                      </button>
                      <div v-if="showNotesSection" class="kg-sec-body">
                        <div v-for="note in nodeNotes" :key="note.id" class="kg-note-item" @click.stop="navigateToNode(note.nodeId)">
                          <span class="kg-note-bar" :style="{ background: note.color || '#6366f1' }"></span>
                          <div class="kg-note-content">
                            <p v-if="note.quote" class="kg-note-quote">{{ note.quote.slice(0, 40) }}{{ note.quote.length > 40 ? '...' : '' }}</p>
                            <p class="kg-note-text">{{ note.content.slice(0, 50) }}{{ note.content.length > 50 ? '...' : '' }}</p>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div v-if="nodeWrongAnswers.length" class="kg-detail-section">
                      <button class="kg-sec-toggle" @click.stop="showWrongSection = !showWrongSection">
                        <span class="kg-sec-icon">❌</span>
                        <span class="kg-sec-label">相关错题</span>
                        <span class="kg-sec-count">{{ nodeWrongAnswers.length }}</span>
                        <span class="kg-sec-arrow" :class="{ 'kg-sec-arrow--open': showWrongSection }">›</span>
                      </button>
                      <div v-if="showWrongSection" class="kg-sec-body">
                        <div v-for="(w, i) in nodeWrongAnswers" :key="w.question + w.nodeId" class="kg-wrong-item">
                          <button class="kg-wrong-head" @click.stop="expandedWrongId = expandedWrongId === w.question ? null : w.question">
                            <span class="kg-wrong-num">{{ i + 1 }}</span>
                            <span class="kg-wrong-q">{{ w.question.slice(0, 36) }}{{ w.question.length > 36 ? '...' : '' }}</span>
                            <span v-if="w.reviewCount > 1" class="kg-wrong-review">复习{{ w.reviewCount }}次</span>
                          </button>
                          <div v-if="expandedWrongId === w.question" class="kg-wrong-body">
                            <div class="kg-wrong-opt kg-wrong-opt--wrong">✗ 你的答案：{{ w.options[w.userIndex] }}</div>
                            <div class="kg-wrong-opt kg-wrong-opt--right">✓ 正确答案：{{ w.options[w.correctIndex] }}</div>
                            <p v-if="w.explanation" class="kg-wrong-exp">{{ w.explanation.slice(0, 80) }}{{ w.explanation.length > 80 ? '...' : '' }}</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div v-if="selectedNode.chapter_id" class="kg-detail-foot">
                    <button class="kg-btn-primary kg-btn-block" @click="navigateToNode(selectedNode.chapter_id)">
                      <el-icon><Position /></el-icon> 前往学习
                    </button>
                  </div>
                </div>
              </Transition>
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
import { useNoteStore } from '../stores/notes'
import { useReviewStore } from '../stores/review'
import { ElMessage } from 'element-plus'
import { Share, Search, Close, MagicStick, Refresh, Download, Position, Plus, Minus, FullScreen } from '@element-plus/icons-vue'
import http from '../utils/http'

const courseStore = useCourseStore()
const noteStore = useNoteStore()
const reviewStore = useReviewStore()
const NODE_W = 160, NODE_H = 42, COL_GAP = 110, ROW_GAP = 16

const loading = ref(false)
const graphData = ref<{ nodes: any[], edges: any[] }>({ nodes: [], edges: [] })
const selectedNode = ref<any>(null)
const searchQuery = ref('')
const canvasRef = ref<HTMLElement | null>(null)
const showEdgeLabels = ref(false)
const highlightedNodes = ref<string[]>([])
const dimmedNodes = ref<string[]>([])
const draggingNode = ref<any>(null)
const dragOffset = ref({ x: 0, y: 0 })
const dragMoved = ref(false)
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0 })
const viewBoxStart = ref({ x: 0, y: 0 })
const viewBox = ref({ x: 0, y: 0, width: 1200, height: 700 })
const showNotesSection = ref(false)
const showWrongSection = ref(false)
const expandedWrongId = ref<string | null>(null)

const viewBoxStr = computed(() => `${viewBox.value.x} ${viewBox.value.y} ${viewBox.value.width} ${viewBox.value.height}`)
const zoomLevel = computed(() => Math.round(1200 / viewBox.value.width * 100))
const hasGraph = computed(() => graphData.value.nodes.length > 0)

const nodeTypes = [
  { value: 'root', label: '课程核心', color: '#6366f1' },
  { value: 'module', label: '模块', color: '#8b5cf6' },
  { value: 'concept', label: '核心概念', color: '#0ea5e9' },
  { value: 'theorem', label: '关键定理', color: '#f43f5e' },
  { value: 'method', label: '核心方法', color: '#10b981' },
  { value: 'application', label: '应用场景', color: '#f59e0b' },
]
const relationColors: Record<string, string> = {
  prerequisite: '#f43f5e', derives: '#6366f1', applies_to: '#0ea5e9',
  contrasts_with: '#10b981', extends: '#8b5cf6', implements: '#6366f1',
  leads_to: '#f59e0b', contains: '#94a3b8', related: '#94a3b8',
}
const relationLabels: Record<string, string> = {
  prerequisite: '前置', derives: '推导', applies_to: '应用',
  contrasts_with: '对比', extends: '扩展', implements: '实现',
  leads_to: '引出', contains: '包含', related: '关联',
}

const getAccent = (node: any) => nodeTypes.find(t => t.value === node.type)?.color ?? '#6366f1'
const getTypeLabel = (type: string) => nodeTypes.find(t => t.value === type)?.label ?? type
const getRelLabel = (rel: string) => relationLabels[rel] ?? rel

const relatedNodes = computed(() => {
  if (!selectedNode.value) return []
  const id = selectedNode.value.id
  const out: { node: any; relation: string }[] = []
  graphData.value.edges.forEach((e: any) => {
    if (e.source === id) { const n = graphData.value.nodes.find((n: any) => n.id === e.target); if (n) out.push({ node: n, relation: e.relation }) }
    else if (e.target === id) { const n = graphData.value.nodes.find((n: any) => n.id === e.source); if (n) out.push({ node: n, relation: e.relation }) }
  })
  return out.slice(0, 6)
})

// 收集选中节点关联的所有课程节点 ID（含子节点）
const selectedNodeIds = computed<Set<string>>(() => {
  if (!selectedNode.value?.chapter_id) return new Set()
  const cid = selectedNode.value.chapter_id
  const ids = new Set<string>([cid])
  if (selectedNode.value.type === 'root' || selectedNode.value.type === 'module') {
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
    .filter(n => ids.has(n.nodeId) && n.sourceType !== 'format')
    .sort((a, b) => b.createdAt - a.createdAt)
    .slice(0, 5)
})

const nodeWrongAnswers = computed(() => {
  const ids = selectedNodeIds.value
  if (ids.size === 0) return []
  return reviewStore.wrongAnswers
    .filter(w => ids.has(w.nodeId))
    .sort((a, b) => b.timestamp - a.timestamp)
    .slice(0, 5)
})

const layoutGraph = () => {
  const { nodes, edges } = graphData.value
  if (!nodes.length) return
  const children: Record<string, string[]> = {}
  nodes.forEach((n: any) => { children[n.id] = [] })
  edges.forEach((e: any) => { children[e.source]?.push(e.target) })
  const level: Record<string, number> = {}
  const root = nodes.find((n: any) => n.type === 'root') ?? nodes[0]
  const q = [root.id]; level[root.id] = 0
  const visited = new Set([root.id])
  while (q.length) {
    const id = q.shift()!
    for (const c of children[id] ?? []) {
      if (!visited.has(c)) { visited.add(c); level[c] = (level[id] ?? 0) + 1; q.push(c) }
    }
  }
  const maxLvl = Math.max(0, ...Object.values(level))
  nodes.forEach((n: any) => { if (level[n.id] === undefined) level[n.id] = maxLvl + 1 })
  const groups: Record<number, any[]> = {}
  nodes.forEach((n: any) => { const l = level[n.id] ?? 0; (groups[l] ??= []).push(n) })
  Object.keys(groups).map(Number).sort((a, b) => a - b).forEach(l => {
    const g = groups[l]
    if (!g) return
    const totalH = g.length * NODE_H + (g.length - 1) * ROW_GAP
    g.forEach((n: any, i: number) => {
      n.x = 80 + l * (NODE_W + COL_GAP)
      n.y = -totalH / 2 + NODE_H / 2 + i * (NODE_H + ROW_GAP)
    })
  })
  for (let iter = 0; iter < 40; iter++) {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j]
        if (Math.abs(a.x - b.x) > NODE_W * 0.8) continue
        const dy = b.y - a.y, min = NODE_H + ROW_GAP
        if (Math.abs(dy) < min) {
          const push = (min - Math.abs(dy)) * 0.5
          const dir = dy >= 0 ? 1 : -1
          a.y -= dir * push; b.y += dir * push
        }
      }
    }
  }
  fitView()
}

const fitView = () => {
  const { nodes } = graphData.value
  if (!nodes.length) return
  const pad = 80
  const xs = nodes.map((n: any) => n.x), ys = nodes.map((n: any) => n.y)
  viewBox.value = {
    x: Math.min(...xs) - NODE_W / 2 - pad,
    y: Math.min(...ys) - NODE_H / 2 - pad,
    width: Math.max(...xs) - Math.min(...xs) + NODE_W + pad * 2,
    height: Math.max(Math.max(...ys) - Math.min(...ys) + NODE_H + pad * 2, 500),
  }
}

const getEdgePath = (edge: any) => {
  const s = graphData.value.nodes.find((n: any) => n.id === edge.source)
  const t = graphData.value.nodes.find((n: any) => n.id === edge.target)
  if (!s || !t) return ''
  const sx = s.x + NODE_W / 2, sy = s.y, tx = t.x - NODE_W / 2, ty = t.y, cx = (sx + tx) / 2
  return `M ${sx} ${sy} C ${cx} ${sy}, ${cx} ${ty}, ${tx} ${ty}`
}
const getEdgeMid = (edge: any) => {
  const s = graphData.value.nodes.find((n: any) => n.id === edge.source)
  const t = graphData.value.nodes.find((n: any) => n.id === edge.target)
  if (!s || !t) return null
  return { x: (s.x + t.x) / 2, y: (s.y + t.y) / 2 }
}
const getEdgeStyle = (edge: any) => {
  const isActive = selectedNode.value && (edge.source === selectedNode.value.id || edge.target === selectedNode.value.id)
  const isDimmed = selectedNode.value && !isActive
  const color = relationColors[edge.relation] ?? '#94a3b8'
  return { stroke: isDimmed ? '#e2e8f0' : isActive ? color : '#c7d2fe', strokeWidth: isActive ? '2.5' : '1.5', opacity: isDimmed ? '0.2' : '1' }
}

const selectNode = (n: any) => { selectedNode.value = n; showNotesSection.value = false; showWrongSection.value = false; expandedWrongId.value = null }
const deselectNode = () => { selectedNode.value = null; showNotesSection.value = false; showWrongSection.value = false; expandedWrongId.value = null }
const handleClose = () => { courseStore.showKnowledgeGraph = false }
const resetView = () => fitView()

const screenToSvg = (cx: number, cy: number) => {
  if (!canvasRef.value) return { x: 0, y: 0 }
  const r = canvasRef.value.getBoundingClientRect()
  return { x: viewBox.value.x + (cx - r.left) * viewBox.value.width / r.width, y: viewBox.value.y + (cy - r.top) * viewBox.value.height / r.height }
}
const startNodeDrag = (node: any, e: MouseEvent) => {
  e.stopPropagation(); draggingNode.value = node; dragMoved.value = false
  const p = screenToSvg(e.clientX, e.clientY)
  dragOffset.value = { x: p.x - node.x, y: p.y - node.y }
}
const startPan = (e: MouseEvent) => {
  const tag = (e.target as Element)?.tagName
  if (!['svg', 'rect', 'path'].includes(tag)) return
  isPanning.value = true; panStart.value = { x: e.clientX, y: e.clientY }
  viewBoxStart.value = { x: viewBox.value.x, y: viewBox.value.y }
}
const onPan = (e: MouseEvent) => {
  if (draggingNode.value) {
    const p = screenToSvg(e.clientX, e.clientY)
    draggingNode.value.x = p.x - dragOffset.value.x; draggingNode.value.y = p.y - dragOffset.value.y
    dragMoved.value = true; return
  }
  if (!isPanning.value || !canvasRef.value) return
  const r = canvasRef.value.getBoundingClientRect()
  viewBox.value.x = viewBoxStart.value.x - (e.clientX - panStart.value.x) * viewBox.value.width / r.width
  viewBox.value.y = viewBoxStart.value.y - (e.clientY - panStart.value.y) * viewBox.value.height / r.height
}
const endPan = () => { draggingNode.value = null; isPanning.value = false }
const handleWheel = (e: WheelEvent) => {
  const scale = e.deltaY > 0 ? 1.12 : 0.88
  const p = screenToSvg(e.clientX, e.clientY)
  viewBox.value.x = p.x - (p.x - viewBox.value.x) * scale; viewBox.value.y = p.y - (p.y - viewBox.value.y) * scale
  viewBox.value.width *= scale; viewBox.value.height *= scale
}
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
const handleSearchInput = () => {
  if (!searchQuery.value.trim()) { highlightedNodes.value = []; dimmedNodes.value = []; return }
  const q = searchQuery.value.toLowerCase()
  highlightedNodes.value = graphData.value.nodes.filter((n: any) => n.label?.toLowerCase().includes(q)).map((n: any) => n.id)
  dimmedNodes.value = graphData.value.nodes.filter((n: any) => !n.label?.toLowerCase().includes(q)).map((n: any) => n.id)
}
const handleSearch = () => {
  const q = searchQuery.value.toLowerCase()
  const found = graphData.value.nodes.find((n: any) => n.label?.toLowerCase().includes(q))
  if (found) { selectNode(found); viewBox.value = { x: found.x - 300, y: found.y - 200, width: 600, height: 400 } }
  else ElMessage.info('未找到匹配节点')
}
const clearSearch = () => { searchQuery.value = ''; highlightedNodes.value = []; dimmedNodes.value = [] }
const navigateToNode = (nodeId: string) => { courseStore.scrollToNode(nodeId); handleClose(); ElMessage.success('已跳转到对应章节') }
const downloadImage = () => {
  if (!canvasRef.value) return
  const svg = canvasRef.value.querySelector('svg'); if (!svg) return
  let src = new XMLSerializer().serializeToString(svg)
  if (!src.includes('xmlns=')) src = src.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"')
  const url = URL.createObjectURL(new Blob([src], { type: 'image/svg+xml' }))
  const a = document.createElement('a'); a.href = url; a.download = `kg-${courseStore.currentCourseId}.svg`
  a.click(); setTimeout(() => URL.revokeObjectURL(url), 100); ElMessage.success('已导出 SVG')
}
const loadGraph = async () => {
  if (!courseStore.currentCourseId) return
  try {
    const res = await http.get(`/api/courses/${courseStore.currentCourseId}/knowledge_graph`)
    if (res.data.status === 'success' && res.data.data.nodes?.length) { graphData.value = res.data.data; layoutGraph() }
  } catch (e) { console.error(e) }
}
const generateGraph = async () => {
  if (!courseStore.currentCourseId) { ElMessage.warning('请先选择课程'); return }
  loading.value = true
  try {
    const res = await http.post(`/api/courses/${courseStore.currentCourseId}/knowledge_graph`)
    if (res.data.status === 'success') { graphData.value = res.data.data; layoutGraph(); ElMessage.success('知识图谱生成成功') }
    else ElMessage.error('生成失败：' + (res.data.message ?? '未知错误'))
  } catch (e: any) { ElMessage.error('生成失败：' + (e.message ?? '网络错误')) }
  finally { loading.value = false }
}
const handleKeydown = (e: KeyboardEvent) => {
  if (!courseStore.showKnowledgeGraph) return
  if (e.key === 'Escape') { if (selectedNode.value) deselectNode(); else handleClose() }
}
watch(() => courseStore.showKnowledgeGraph, show => {
  if (show) { loadGraph(); document.addEventListener('keydown', handleKeydown) }
  else { document.removeEventListener('keydown', handleKeydown); selectedNode.value = null; searchQuery.value = '' }
})
watch(() => courseStore.currentCourseId, () => { if (courseStore.showKnowledgeGraph) loadGraph() })
</script>

<style scoped>
.kg-overlay { position: fixed; inset: 0; z-index: 100; background: rgba(15,23,42,0.45); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; padding: 24px; }
.kg-container { width: 100%; height: 100%; max-width: 1400px; max-height: 900px; background: #fff; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.16); display: flex; flex-direction: column; overflow: hidden; }
.kg-header { display: flex; align-items: center; gap: 14px; padding: 11px 18px; border-bottom: 1px solid #e2e8f0; background: #fff; flex-shrink: 0; }
.kg-header-left { display: flex; align-items: center; gap: 9px; }
.kg-icon-wrap { width: 32px; height: 32px; border-radius: 8px; background: linear-gradient(135deg,#6366f1,#8b5cf6); display: flex; align-items: center; justify-content: center; color: #fff; }
.kg-title { font-size: 14px; font-weight: 700; color: #0f172a; }
.kg-header-center { flex: 1; max-width: 340px; }
.kg-search-wrap { position: relative; display: flex; align-items: center; }
.kg-search-ico { position: absolute; left: 9px; color: #94a3b8; font-size: 13px; }
.kg-search-input { width: 100%; padding: 6px 30px 6px 30px; border: 1px solid #e2e8f0; border-radius: 9px; font-size: 12px; color: #1e293b; background: #f8fafc; transition: all .2s; }
.kg-search-input:focus { outline: none; border-color: #6366f1; background: #fff; box-shadow: 0 0 0 3px rgba(99,102,241,.1); }
.kg-search-input::placeholder { color: #94a3b8; }
.kg-search-clear { position: absolute; right: 7px; background: none; border: none; color: #94a3b8; cursor: pointer; padding: 2px; display: flex; border-radius: 4px; }
.kg-search-clear:hover { color: #64748b; background: #f1f5f9; }
.kg-header-right { display: flex; align-items: center; gap: 5px; margin-left: auto; }
.kg-hbtn { display: inline-flex; align-items: center; gap: 4px; padding: 5px 10px; border-radius: 7px; border: 1px solid #e2e8f0; background: #f8fafc; font-size: 12px; font-weight: 500; color: #475569; cursor: pointer; transition: all .15s; }
.kg-hbtn:hover:not(:disabled) { background: #fff; color: #1e293b; border-color: #cbd5e1; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.kg-hbtn:disabled { opacity: .5; cursor: not-allowed; }
.kg-btn-primary { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 9px; border: none; background: linear-gradient(135deg,#6366f1,#8b5cf6); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; box-shadow: 0 3px 10px rgba(99,102,241,.3); transition: all .2s; }
.kg-btn-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 5px 16px rgba(99,102,241,.4); }
.kg-btn-primary:disabled { opacity: .45; cursor: not-allowed; }
.kg-btn-lg { padding: 10px 20px; font-size: 14px; border-radius: 11px; }
.kg-btn-block { width: 100%; justify-content: center; }
.kg-close { width: 32px; height: 32px; border-radius: 8px; border: 1px solid #e2e8f0; background: #f8fafc; color: #64748b; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s; }
.kg-close:hover { background: #fee2e2; color: #ef4444; border-color: #fca5a5; }
.kg-body { flex: 1; position: relative; overflow: hidden; }
.kg-canvas { width: 100%; height: 100%; position: relative; cursor: grab; overflow: hidden; }
.kg-canvas:active { cursor: grabbing; }
.kg-svg { width: 100%; height: 100%; display: block; }
.kg-node { cursor: pointer; transition: opacity .2s; }
.kg-node--dim { opacity: .25; }
.kg-nlabel { font-size: 11px; dominant-baseline: middle; text-anchor: start; pointer-events: none; user-select: none; }
.kg-elabel { font-size: 9px; fill: #94a3b8; text-anchor: middle; dominant-baseline: auto; pointer-events: none; user-select: none; }
.kg-empty { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; }
.kg-empty-icon { color: #c7d2fe; }
.kg-empty-title { font-size: 16px; font-weight: 600; color: #1e293b; margin: 0; }
.kg-empty-sub { font-size: 13px; color: #94a3b8; margin: 0; }
.kg-loading { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; }
.kg-spin { display: flex; gap: 8px; }
.kg-spin div { width: 10px; height: 10px; border-radius: 50%; background: #6366f1; animation: kg-bounce 1.2s infinite ease-in-out; }
.kg-spin div:nth-child(2) { animation-delay: .2s; }
.kg-spin div:nth-child(3) { animation-delay: .4s; }
@keyframes kg-bounce { 0%,80%,100%{transform:scale(0)} 40%{transform:scale(1)} }
.kg-loading-t { font-size: 14px; font-weight: 600; color: #1e293b; margin: 0; }
.kg-loading-s { font-size: 12px; color: #94a3b8; margin: 0; }
.kg-legend { position: absolute; left: 16px; bottom: 16px; background: rgba(255,255,255,.95); border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px; backdrop-filter: blur(8px); box-shadow: 0 2px 12px rgba(0,0,0,.08); }
.kg-legend-title { font-size: 11px; font-weight: 700; color: #64748b; margin-bottom: 7px; text-transform: uppercase; letter-spacing: .05em; }
.kg-legend-items { display: flex; flex-direction: column; gap: 5px; }
.kg-legend-item { display: flex; align-items: center; gap: 7px; }
.kg-legend-bar { display: inline-block; width: 4px; height: 14px; border-radius: 2px; flex-shrink: 0; }
.kg-legend-label { font-size: 11px; color: #475569; }
.kg-legend-toggle { margin-top: 8px; width: 100%; padding: 4px 0; border: 1px solid #e2e8f0; border-radius: 6px; background: #f8fafc; font-size: 11px; color: #64748b; cursor: pointer; transition: all .15s; }
.kg-legend-toggle:hover { background: #f1f5f9; color: #1e293b; }
.kg-zoom { position: absolute; right: 16px; bottom: 16px; display: flex; flex-direction: column; align-items: center; gap: 2px; background: rgba(255,255,255,.95); border: 1px solid #e2e8f0; border-radius: 10px; padding: 6px; box-shadow: 0 2px 12px rgba(0,0,0,.08); }
.kg-zbtn { width: 28px; height: 28px; border-radius: 6px; border: none; background: none; color: #475569; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s; }
.kg-zbtn:hover { background: #f1f5f9; color: #1e293b; }
.kg-zlevel { font-size: 10px; color: #94a3b8; padding: 2px 0; }
.kg-stats { position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%); background: rgba(255,255,255,.9); border: 1px solid #e2e8f0; border-radius: 20px; padding: 4px 14px; font-size: 11px; color: #64748b; box-shadow: 0 1px 6px rgba(0,0,0,.06); }
.kg-detail { position: absolute; top: 16px; right: 16px; width: 240px; background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px; box-shadow: 0 4px 20px rgba(0,0,0,.1); max-height: calc(100% - 32px); overflow-y: auto; }
.kg-detail-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.kg-detail-badge { font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 20px; }
.kg-detail-close { width: 24px; height: 24px; border-radius: 6px; border: none; background: #f1f5f9; color: #64748b; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.kg-detail-close:hover { background: #fee2e2; color: #ef4444; }
.kg-detail-title { font-size: 14px; font-weight: 700; color: #0f172a; margin: 0 0 8px; }
.kg-detail-desc { font-size: 12px; color: #64748b; line-height: 1.6; margin: 0 0 12px; }
.kg-detail-sec { font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px; }
.kg-detail-related { margin-bottom: 12px; }
.kg-rel-item { display: flex; align-items: center; gap: 7px; width: 100%; padding: 5px 7px; border-radius: 7px; border: none; background: none; cursor: pointer; text-align: left; transition: background .15s; }
.kg-rel-item:hover { background: #f8fafc; }
.kg-rel-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.kg-rel-name { font-size: 12px; color: #334155; flex: 1; }
.kg-rel-tag { font-size: 10px; color: #94a3b8; }
.kg-detail-foot { border-top: 1px solid #f1f5f9; padding-top: 10px; }
.modal-enter-active, .modal-leave-active { transition: all .25s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-from .kg-container, .modal-leave-to .kg-container { transform: scale(.96); }
.slide-in-enter-active, .slide-in-leave-active { transition: all .2s ease; }
.slide-in-enter-from, .slide-in-leave-to { opacity: 0; transform: translateX(16px); }
.kg-detail-extra { margin-bottom: 12px; border-top: 1px solid #f1f5f9; padding-top: 10px; }
.kg-detail-section { margin-bottom: 8px; }
.kg-sec-toggle { display: flex; align-items: center; gap: 6px; width: 100%; padding: 5px 6px; border-radius: 7px; border: none; background: #f8fafc; cursor: pointer; transition: background .15s; font-size: 12px; }
.kg-sec-toggle:hover { background: #f1f5f9; }
.kg-sec-icon { font-size: 13px; flex-shrink: 0; }
.kg-sec-label { font-size: 11px; font-weight: 600; color: #475569; flex: 1; text-align: left; }
.kg-sec-count { font-size: 10px; color: #94a3b8; background: #f1f5f9; padding: 1px 6px; border-radius: 10px; }
.kg-sec-arrow { font-size: 14px; color: #94a3b8; transition: transform .2s; display: inline-block; }
.kg-sec-arrow--open { transform: rotate(90deg); }
.kg-sec-body { margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
.kg-note-item { display: flex; gap: 7px; padding: 5px 6px; border-radius: 6px; cursor: pointer; transition: background .15s; }
.kg-note-item:hover { background: #f8fafc; }
.kg-note-bar { width: 3px; border-radius: 2px; flex-shrink: 0; align-self: stretch; }
.kg-note-content { flex: 1; min-width: 0; }
.kg-note-quote { font-size: 10px; color: #94a3b8; margin: 0 0 2px; font-style: italic; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kg-note-text { font-size: 11px; color: #475569; margin: 0; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kg-wrong-item { border-radius: 6px; overflow: hidden; }
.kg-wrong-head { display: flex; align-items: center; gap: 6px; width: 100%; padding: 5px 6px; border: none; background: none; cursor: pointer; transition: background .15s; text-align: left; }
.kg-wrong-head:hover { background: #fef2f2; }
.kg-wrong-num { width: 18px; height: 18px; border-radius: 50%; background: #fee2e2; color: #ef4444; font-size: 10px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.kg-wrong-q { font-size: 11px; color: #334155; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kg-wrong-review { font-size: 9px; color: #94a3b8; flex-shrink: 0; }
.kg-wrong-body { padding: 4px 6px 8px 30px; }
.kg-wrong-opt { font-size: 11px; line-height: 1.6; }
.kg-wrong-opt--wrong { color: #ef4444; }
.kg-wrong-opt--right { color: #10b981; }
.kg-wrong-exp { font-size: 10px; color: #64748b; margin: 4px 0 0; line-height: 1.5; }
</style>
