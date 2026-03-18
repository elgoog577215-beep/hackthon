<template>
  <div ref="canvasRef" class="kgc-canvas" @click="handleCanvasClick">
    <svg v-if="nodes.length" :viewBox="viewBoxStr" class="kgc-svg"
      @wheel.prevent="handleWheel"
      @mousedown="startPan" @mousemove="onMouseMove"
      @mouseup="endInteraction" @mouseleave="endInteraction">

      <defs>
        <!-- 节点发光滤镜 -->
        <filter v-for="nt in nodeTypeColors" :key="'glow-'+nt.type" :id="'glow-'+nt.type"
          x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur :in="'SourceGraphic'" :stdDeviation="4" result="blur"/>
          <feFlood :flood-color="nt.color" flood-opacity="0.6" result="color"/>
          <feComposite in="color" in2="blur" operator="in" result="glow"/>
          <feMerge>
            <feMergeNode in="glow"/>
            <feMergeNode in="glow"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
        <!-- 选中节点强发光 -->
        <filter id="glow-selected" x="-150%" y="-150%" width="400%" height="400%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur"/>
          <feFlood flood-color="#ffffff" flood-opacity="0.5" result="color"/>
          <feComposite in="color" in2="blur" operator="in" result="glow"/>
          <feMerge>
            <feMergeNode in="glow"/>
            <feMergeNode in="glow"/>
            <feMergeNode in="glow"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>

      <!-- 深色背景 -->
      <rect :x="vb.x-4000" :y="vb.y-4000" :width="vb.width+8000" :height="vb.height+8000" fill="#1a1b2e"/>

      <!-- 点阵背景 -->
      <g opacity="0.08">
        <circle v-for="dot in bgDots" :key="dot.key"
          :cx="dot.x" :cy="dot.y" r="1" fill="#8b8fa3"/>
      </g>

      <!-- 连线模式预览线 -->
      <line v-if="linkMode && linkPreviewStart && linkPreviewEnd"
        :x1="linkPreviewStart.x" :y1="linkPreviewStart.y" :x2="linkPreviewEnd.x" :y2="linkPreviewEnd.y"
        stroke="#a78bfa" stroke-width="1.5" stroke-dasharray="6,4" opacity="0.6"/>

      <!-- 边：柔和曲线 -->
      <g v-for="edge in edges" :key="edge.id || (edge.source+'-'+edge.target)">
        <!-- 透明宽路径用于扩大点击区域 -->
        <path
          :d="getEdgePath(edge)"
          fill="none" stroke="transparent" stroke-width="12"
          class="kgc-edge-hitarea"
          @click.stop="$emit('selectEdge', edge)"/>
        <path
          :d="getEdgePath(edge)"
          :style="getEdgeStyle(edge)"
          fill="none" pointer-events="none"
          class="kgc-edge"/>
        <text v-if="showEdgeLabels && getEdgeMid(edge)"
          :x="getEdgeMid(edge)!.x" :y="getEdgeMid(edge)!.y - 10"
          class="kgc-elabel">{{ getEdgeDisplayLabel(edge) }}</text>
      </g>

      <!-- 节点 -->
      <g v-for="node in nodes" :key="node.id"
        :class="['kgc-node', {
          'kgc-node--sel': selectedNodeId === node.id,
          'kgc-node--dim': dimmedNodes.has(node.id),
          'kgc-node--link-target': linkMode && linkSource && linkSource.id !== node.id,
        }]"
        :transform="`translate(${node.x},${node.y})`"
        @mousedown.stop="startNodeDrag(node, $event)"
        @click.stop="handleNodeClick(node)">

        <!-- 呼吸光环（仅选中节点） -->
        <circle v-if="selectedNodeId === node.id" r="22"
          :fill="getNodeColor(node)" opacity="0.12" class="kgc-pulse"/>

        <!-- 外圈光晕 -->
        <circle
          :r="node.type === 'root' ? 12 : 8"
          :fill="getNodeColor(node)" opacity="0.15" class="kgc-halo"/>

        <!-- 核心圆点 -->
        <circle
          :r="node.type === 'root' ? 6 : 4"
          :fill="getNodeColor(node)"
          :filter="selectedNodeId === node.id ? 'url(#glow-selected)' : `url(#glow-${node.type})`"
          class="kgc-dot"/>

        <!-- 标签 -->
        <text :y="node.type === 'root' ? 22 : 18" class="kgc-nlabel"
          :class="{
            'kgc-nlabel--root': node.type === 'root',
            'kgc-nlabel--sel': selectedNodeId === node.id,
          }"
          :fill="selectedNodeId === node.id ? '#e2e8f0' : '#8b8fa3'">
          {{ node.label }}
        </text>
      </g>
    </svg>

    <!-- 空状态 -->
    <div v-if="!nodes.length && !loading" class="kgc-empty">
      <div class="kgc-empty-icon"><el-icon :size="36"><Share /></el-icon></div>
      <p class="kgc-empty-title">知识图谱</p>
      <p class="kgc-empty-sub">AI 生成或手动创建概念关系网络</p>
      <div class="kgc-empty-actions">
        <button class="kgc-btn-primary kgc-btn-lg" @click="$emit('generate')">
          <el-icon><MagicStick /></el-icon> AI 生成
        </button>
        <button class="kgc-btn-secondary kgc-btn-lg" @click="$emit('addNode')">
          <el-icon><Plus /></el-icon> 手动创建
        </button>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="kgc-loading">
      <div class="kgc-spin"><div/><div/><div/></div>
      <p class="kgc-loading-t">正在生成知识图谱...</p>
      <p class="kgc-loading-s">AI 正在分析课程内容，构建概念关系</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { Share, MagicStick, Plus } from '@element-plus/icons-vue'
import {
  getNodeColor, getRelationColor, getRelationLabel,
  type KGNode, type KGEdge,
} from '../../types/knowledge-graph'

const props = defineProps<{
  nodes: KGNode[]
  edges: KGEdge[]
  selectedNodeId: string | null
  selectedEdgeId: string | null
  showEdgeLabels: boolean
  loading: boolean
  linkMode: boolean
  linkSource: KGNode | null
}>()

const emit = defineEmits<{
  (e: 'selectNode', node: KGNode): void
  (e: 'selectEdge', edge: KGEdge): void
  (e: 'deselectAll'): void
  (e: 'nodePositionChanged', nodeId: string, x: number, y: number): void
  (e: 'generate'): void
  (e: 'addNode'): void
  (e: 'linkTarget', node: KGNode): void
}>()

const canvasRef = ref<HTMLElement | null>(null)
const draggingNode = ref<KGNode | null>(null)
const dragOffset = ref({ x: 0, y: 0 })
const dragMoved = ref(false)
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0 })
const viewBoxStart = ref({ x: 0, y: 0 })
const mousePos = ref<{ x: number; y: number } | null>(null)
/** 记录最后一次鼠标屏幕坐标，用于在 simTick 变化时重新计算 SVG 坐标 */
const lastScreenPos = ref<{ x: number; y: number } | null>(null)

/** 力模拟的 tick 计数器，用于触发 Vue 响应式更新 */
const simTick = ref(0)

const vb = ref({ x: 0, y: 0, width: 1200, height: 700 })
const viewBoxStr = computed(() => {
  // 依赖 simTick 以便力模拟每帧都能刷新 viewBox 相关的渲染
  void simTick.value
  return `${vb.value.x} ${vb.value.y} ${vb.value.width} ${vb.value.height}`
})

/** 节点类型对应颜色（用于 SVG filter） */
const nodeTypeColors = [
  { type: 'root', color: '#6366f1' },
  { type: 'concept', color: '#0ea5e9' },
  { type: 'theorem', color: '#f43f5e' },
  { type: 'method', color: '#10b981' },
  { type: 'application', color: '#f59e0b' },
  { type: 'custom', color: '#8b5cf6' },
]

/** 背景点阵（稀疏） */
const bgDots = computed(() => {
  const dots: { key: string; x: number; y: number }[] = []
  const step = 60
  const sx = Math.floor(vb.value.x / step) * step
  const sy = Math.floor(vb.value.y / step) * step
  for (let x = sx; x < vb.value.x + vb.value.width; x += step) {
    for (let y = sy; y < vb.value.y + vb.value.height; y += step) {
      dots.push({ key: `${x}_${y}`, x, y })
    }
  }
  return dots
})

const dimmedNodes = computed(() => {
  void simTick.value
  if (!props.selectedNodeId) return new Set<string>()
  const active = new Set<string>([props.selectedNodeId])
  props.edges.forEach(e => {
    if (e.source === props.selectedNodeId) active.add(e.target)
    if (e.target === props.selectedNodeId) active.add(e.source)
  })
  return new Set(props.nodes.filter(n => !active.has(n.id)).map(n => n.id))
})

// =============================================
// 持续力导向模拟（Obsidian 风格灵动效果）
// =============================================
interface SimState {
  vx: Record<string, number>
  vy: Record<string, number>
  alpha: number       // 当前模拟温度
  alphaTarget: number // 目标温度
  rafId: number | null
}

const sim: SimState = {
  vx: {}, vy: {},
  alpha: 0,
  alphaTarget: 0.02,  // 静息态微弱温度，保持轻微浮动
  rafId: null,
}

const SIM_ALPHA_DECAY = 0.012     // 温度衰减速率
const SIM_VELOCITY_DECAY = 0.35   // 速度衰减（高阻尼 = 柔和运动）
const SIM_REPULSION = 5000        // 斥力系数
const SIM_MIN_DIST = 80           // 最小节点间距
const SIM_COLLISION_RADIUS = 100  // 碰撞半径：节点间距小于此值时强制分离（不受 alpha 衰减影响）
const SIM_COLLISION_STRENGTH = 0.8 // 碰撞分离力强度
const SIM_CENTER_STRENGTH = 0.003 // 居中力

/** 启动/重启模拟（升温） */
const heatSimulation = (alpha = 0.3) => {
  sim.alpha = Math.max(sim.alpha, alpha)
  // 确保所有节点都有速度
  props.nodes.forEach(n => {
    if (!(n.id in sim.vx)) { sim.vx[n.id] = 0; sim.vy[n.id] = 0 }
  })
  if (!sim.rafId) tickSimulation()
}

/** 停止模拟 */
const stopSimulation = () => {
  if (sim.rafId) { cancelAnimationFrame(sim.rafId); sim.rafId = null }
}

/** 每帧力模拟 */
const tickSimulation = () => {
  const { nodes, edges } = props
  if (!nodes.length) { sim.rafId = null; return }

  // 温度衰减
  sim.alpha += (sim.alphaTarget - sim.alpha) * SIM_ALPHA_DECAY

  const nodeById: Record<string, KGNode> = {}
  nodes.forEach(n => { nodeById[n.id] = n })

  // 累积力
  const fx: Record<string, number> = {}
  const fy: Record<string, number> = {}
  nodes.forEach(n => { fx[n.id] = 0; fy[n.id] = 0 })

  // 1) 斥力：所有节点对
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i]!, b = nodes[j]!
      let dx = b.x - a.x, dy = b.y - a.y
      let dist = Math.sqrt(dx * dx + dy * dy) || 1
      if (dist < SIM_MIN_DIST) dist = SIM_MIN_DIST
      const force = SIM_REPULSION * sim.alpha / (dist * dist)
      const ux = (dx / dist) * force, uy = (dy / dist) * force
      fx[a.id] = (fx[a.id] ?? 0) - ux; fy[a.id] = (fy[a.id] ?? 0) - uy
      fx[b.id] = (fx[b.id] ?? 0) + ux; fy[b.id] = (fy[b.id] ?? 0) + uy
    }
  }

  // 2) 弹簧引力：沿边，权重越大弹簧越强、理想距离越短
  //    weight 1  → idealDist 350, strength 0.008  (弱关联，远距离)
  //    weight 5  → idealDist 220, strength 0.05   (中等关联)
  //    weight 10 → idealDist 120, strength 0.15   (核心依赖，但不低于碰撞半径)
  for (const edge of edges) {
    const s = nodeById[edge.source], t = nodeById[edge.target]
    if (!s || !t) continue
    const w = edge.weight ?? 5
    const wNorm = (w - 1) / 9  // 归一化到 0~1
    const idealDist = 350 - wNorm * 230
    const strength = 0.008 + wNorm * wNorm * 0.142  // 二次曲线，高权重效果更显著
    let dx = t.x - s.x, dy = t.y - s.y
    const dist = Math.sqrt(dx * dx + dy * dy) || 1
    const force = (dist - idealDist) * strength * sim.alpha
    const ux = (dx / dist) * force, uy = (dy / dist) * force
    fx[s.id] = (fx[s.id] ?? 0) + ux; fy[s.id] = (fy[s.id] ?? 0) + uy
    fx[t.id] = (fx[t.id] ?? 0) - ux; fy[t.id] = (fy[t.id] ?? 0) - uy
  }

  // 3) 轻微居中力
  const cx = nodes.reduce((s, n) => s + n.x, 0) / nodes.length
  const cy = nodes.reduce((s, n) => s + n.y, 0) / nodes.length
  nodes.forEach(n => {
    fx[n.id] = (fx[n.id] ?? 0) + (cx - n.x) * SIM_CENTER_STRENGTH * sim.alpha * 0.5
    fy[n.id] = (fy[n.id] ?? 0) + (cy - n.y) * SIM_CENTER_STRENGTH * sim.alpha * 0.5
  })

  // 4) 碰撞分离：不受 alpha 衰减影响，确保节点永远不会重叠
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i]!, b = nodes[j]!
      let dx = b.x - a.x, dy = b.y - a.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.1
      if (dist < SIM_COLLISION_RADIUS) {
        // 线性递增的分离力：越近越强
        const overlap = SIM_COLLISION_RADIUS - dist
        const push = overlap * SIM_COLLISION_STRENGTH / dist
        // 完全重合时给随机方向避免死锁
        if (dist < 1) { dx = Math.random() - 0.5; dy = Math.random() - 0.5 }
        fx[a.id] = (fx[a.id] ?? 0) - dx * push; fy[a.id] = (fy[a.id] ?? 0) - dy * push
        fx[b.id] = (fx[b.id] ?? 0) + dx * push; fy[b.id] = (fy[b.id] ?? 0) + dy * push
      }
    }
  }

  // 应用力 → 速度 → 位置
  let totalMovement = 0
  nodes.forEach(n => {
    // 被拖拽的节点不受力影响
    if (draggingNode.value?.id === n.id) {
      sim.vx[n.id] = 0; sim.vy[n.id] = 0
      return
    }
    const vx = sim.vx[n.id] ?? 0
    const vy = sim.vy[n.id] ?? 0
    const fxVal = fx[n.id] ?? 0
    const fyVal = fy[n.id] ?? 0
    sim.vx[n.id] = (vx + fxVal) * (1 - SIM_VELOCITY_DECAY)
    sim.vy[n.id] = (vy + fyVal) * (1 - SIM_VELOCITY_DECAY)
    // 限速
    const speed = Math.sqrt((sim.vx[n.id] ?? 0) ** 2 + (sim.vy[n.id] ?? 0) ** 2)
    const maxSpeed = 8
    if (speed > maxSpeed) {
      sim.vx[n.id] = ((sim.vx[n.id] ?? 0) / speed) * maxSpeed
      sim.vy[n.id] = ((sim.vy[n.id] ?? 0) / speed) * maxSpeed
    }
    n.x += sim.vx[n.id] ?? 0
    n.y += sim.vy[n.id] ?? 0
    totalMovement += Math.abs(sim.vx[n.id] ?? 0) + Math.abs(sim.vy[n.id] ?? 0)
  })

  // 触发 Vue 响应式更新
  simTick.value++

  // 继续循环（即使几乎静止也保持微弱运动）
  sim.rafId = requestAnimationFrame(tickSimulation)
}

// 监听节点/边变化 → 重新升温
watch(() => [props.nodes.length, props.edges.length], () => {
  if (props.nodes.length) heatSimulation(0.5)
}, { flush: 'post' })

onBeforeUnmount(() => stopSimulation())

// --- 节点位置查找（依赖 simTick 触发每帧更新） ---
const nodePos = (id: string) => {
  void simTick.value
  const n = props.nodes.find(n => n.id === id)
  return n ? { x: n.x, y: n.y } : { x: 0, y: 0 }
}

/** 连线模式预览线的终点坐标，每帧随 simTick 重新计算以跟踪鼠标真实 SVG 位置 */
const linkPreviewEnd = computed(() => {
  void simTick.value
  if (!lastScreenPos.value) return mousePos.value
  return screenToSvg(lastScreenPos.value.x, lastScreenPos.value.y)
})

/** 连线模式预览线的起点坐标，每帧随 simTick 更新以跟踪源节点位置 */
const linkPreviewStart = computed(() => {
  void simTick.value
  if (!props.linkSource) return null
  return { x: props.linkSource.x, y: props.linkSource.y }
})

// --- Edge rendering ---
const getEdgeMid = (edge: KGEdge) => {
  const s = props.nodes.find(n => n.id === edge.source)
  const t = props.nodes.find(n => n.id === edge.target)
  if (!s || !t) return null
  return { x: (s.x + t.x) / 2, y: (s.y + t.y) / 2 }
}

/** 生成柔和曲线路径 */
const getEdgePath = (edge: KGEdge) => {
  const s = nodePos(edge.source)
  const t = nodePos(edge.target)
  const dx = t.x - s.x
  const dy = t.y - s.y
  const dist = Math.sqrt(dx * dx + dy * dy)
  // 曲率随距离自适应，近距离几乎直线，远距离微弯
  const curvature = Math.min(dist * 0.15, 40)
  // 法线方向偏移
  const nx = -dy / (dist || 1) * curvature
  const ny = dx / (dist || 1) * curvature
  const mx = (s.x + t.x) / 2 + nx
  const my = (s.y + t.y) / 2 + ny
  return `M ${s.x} ${s.y} Q ${mx} ${my} ${t.x} ${t.y}`
}

const getEdgeStyle = (edge: KGEdge) => {
  const isSelected = props.selectedEdgeId === edge.id
  const isNodeActive = props.selectedNodeId && (edge.source === props.selectedNodeId || edge.target === props.selectedNodeId)
  const isDimmed = props.selectedNodeId && !isNodeActive
  const w = edge.weight ?? 5
  const wNorm = (w - 1) / 9  // 0~1
  // 权重影响线宽和透明度，让差异一目了然
  const baseOpacity = 0.06 + wNorm * 0.4
  const baseWidth = 0.5 + wNorm * 1.5
  return {
    stroke: isSelected ? '#a78bfa' : isNodeActive ? getRelationColor(edge.relation) : '#4a4e6a',
    strokeWidth: isSelected ? '2.5' : isNodeActive ? '2' : String(baseWidth),
    opacity: isDimmed ? '0.03' : String(isNodeActive || isSelected ? 0.8 : baseOpacity),
  }
}

const getEdgeDisplayLabel = (edge: KGEdge) => edge.label || getRelationLabel(edge.relation)

// --- Coordinate conversion ---
const screenToSvg = (cx: number, cy: number) => {
  if (!canvasRef.value) return { x: 0, y: 0 }
  const r = canvasRef.value.getBoundingClientRect()
  return {
    x: vb.value.x + (cx - r.left) * vb.value.width / r.width,
    y: vb.value.y + (cy - r.top) * vb.value.height / r.height,
  }
}

// --- Node drag ---
const startNodeDrag = (node: KGNode, e: MouseEvent) => {
  if (props.linkMode) return
  draggingNode.value = node
  dragMoved.value = false
  const p = screenToSvg(e.clientX, e.clientY)
  dragOffset.value = { x: p.x - node.x, y: p.y - node.y }
  // 拖拽时升温，让周围节点实时反应
  heatSimulation(0.4)
}

// --- Pan ---
const startPan = (e: MouseEvent) => {
  if (props.linkMode) {
    lastScreenPos.value = { x: e.clientX, y: e.clientY }
    mousePos.value = screenToSvg(e.clientX, e.clientY)
    return
  }
  const tag = (e.target as Element)?.tagName
  if (!['svg', 'rect', 'line', 'circle', 'path'].includes(tag)) return
  isPanning.value = true
  panStart.value = { x: e.clientX, y: e.clientY }
  viewBoxStart.value = { x: vb.value.x, y: vb.value.y }
}

const onMouseMove = (e: MouseEvent) => {
  if (props.linkMode) {
    lastScreenPos.value = { x: e.clientX, y: e.clientY }
    mousePos.value = screenToSvg(e.clientX, e.clientY)
  }
  if (draggingNode.value) {
    const p = screenToSvg(e.clientX, e.clientY)
    draggingNode.value.x = p.x - dragOffset.value.x
    draggingNode.value.y = p.y - dragOffset.value.y
    dragMoved.value = true
    return
  }
  if (!isPanning.value || !canvasRef.value) return
  const r = canvasRef.value.getBoundingClientRect()
  vb.value.x = viewBoxStart.value.x - (e.clientX - panStart.value.x) * vb.value.width / r.width
  vb.value.y = viewBoxStart.value.y - (e.clientY - panStart.value.y) * vb.value.height / r.height
}

const endInteraction = () => {
  if (draggingNode.value && dragMoved.value) {
    emit('nodePositionChanged', draggingNode.value.id, draggingNode.value.x, draggingNode.value.y)
    // 松手后轻微升温让图谱自然回弹稳定
    heatSimulation(0.15)
  }
  draggingNode.value = null
  isPanning.value = false
  if (!props.linkMode) {
    mousePos.value = null
    lastScreenPos.value = null
  }
}

// --- Zoom ---
const handleWheel = (e: WheelEvent) => {
  const scale = e.deltaY > 0 ? 1.12 : 0.88
  const p = screenToSvg(e.clientX, e.clientY)
  vb.value.x = p.x - (p.x - vb.value.x) * scale
  vb.value.y = p.y - (p.y - vb.value.y) * scale
  vb.value.width *= scale
  vb.value.height *= scale
}

// --- Click handlers ---
const handleNodeClick = (node: KGNode) => {
  // 连线模式下跳过拖拽检查（linkMode 时 startNodeDrag 直接 return，dragMoved 不会被重置）
  if (!props.linkMode && dragMoved.value) return
  if (props.linkMode) {
    emit('linkTarget', node)
  } else {
    emit('selectNode', node)
  }
}

const handleCanvasClick = (e: MouseEvent) => {
  const tag = (e.target as Element)?.tagName
  if (['svg', 'rect'].includes(tag) || (e.target as Element)?.classList?.contains('kgc-canvas')) {
    emit('deselectAll')
  }
}

// --- Public methods ---
const zoomIn = () => {
  const cx = vb.value.x + vb.value.width / 2, cy = vb.value.y + vb.value.height / 2
  vb.value.width *= 0.8; vb.value.height *= 0.8
  vb.value.x = cx - vb.value.width / 2; vb.value.y = cy - vb.value.height / 2
}

const zoomOut = () => {
  const cx = vb.value.x + vb.value.width / 2, cy = vb.value.y + vb.value.height / 2
  vb.value.width *= 1.25; vb.value.height *= 1.25
  vb.value.x = cx - vb.value.width / 2; vb.value.y = cy - vb.value.height / 2
}

const fitView = () => {
  if (!props.nodes.length) return
  const pad = 120
  const xs = props.nodes.map(n => n.x), ys = props.nodes.map(n => n.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const w = maxX - minX + pad * 2
  const h = maxY - minY + pad * 2
  vb.value = {
    x: minX - pad,
    y: minY - pad,
    width: Math.max(w, 600),
    height: Math.max(h, 400),
  }
}

const focusNode = (node: KGNode) => {
  vb.value = { x: node.x - 300, y: node.y - 200, width: 600, height: 400 }
}

const getZoomLevel = () => {
  const w = vb.value.width
  if (!w || isNaN(w) || w <= 0) return 100
  return Math.round(1200 / w * 100)
}

const getCanvasElement = () => canvasRef.value

defineExpose({ zoomIn, zoomOut, fitView, focusNode, getZoomLevel, getCanvasElement, vb, heatSimulation, stopSimulation })
</script>

<style scoped>
.kgc-canvas { width: 100%; height: 100%; position: relative; cursor: grab; overflow: hidden; background: #1a1b2e; }
.kgc-canvas:active { cursor: grabbing; }
.kgc-svg { width: 100%; height: 100%; display: block; }

/* 边：柔和曲线 */
.kgc-edge { transition: opacity .3s, stroke .3s; }
.kgc-edge-hitarea { cursor: pointer; }
.kgc-edge-hitarea:hover + .kgc-edge { stroke: #a78bfa !important; opacity: 0.8 !important; stroke-width: 2 !important; }
.kgc-elabel { font-size: 9px; fill: #6b7094; text-anchor: middle; pointer-events: none; user-select: none; }

/* 节点 */
.kgc-node { cursor: pointer; transition: opacity .4s ease; }
.kgc-node--dim { opacity: .08; }
.kgc-node--link-target { cursor: crosshair; }

/* 光晕 */
.kgc-halo { transition: r .3s ease, opacity .3s ease; }
.kgc-node:hover .kgc-halo { r: 16; opacity: 0.25; }

/* 核心圆点 */
.kgc-dot { transition: r .25s ease, fill .2s; }
.kgc-node:hover .kgc-dot { r: 6; }

/* 呼吸脉冲动画 */
.kgc-pulse { animation: kgc-breathe 2.4s ease-in-out infinite; transform-origin: center; }
@keyframes kgc-breathe {
  0%, 100% { r: 18; opacity: 0.08; }
  50% { r: 26; opacity: 0.18; }
}

/* 标签 */
.kgc-nlabel { font-size: 11px; text-anchor: middle; dominant-baseline: hanging; pointer-events: none; user-select: none; font-weight: 500; transition: fill .2s; }
.kgc-nlabel--root { font-size: 12px; fill: #c4c9e2; font-weight: 700; }
.kgc-nlabel--sel { fill: #e2e8f0 !important; font-weight: 600; }
.kgc-node:hover .kgc-nlabel { fill: #c4c9e2; }

/* 空状态 */
.kgc-empty { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; background: #1a1b2e; }
.kgc-empty-icon { color: #4a4e6a; }
.kgc-empty-title { font-size: 16px; font-weight: 600; color: #c4c9e2; margin: 0; }
.kgc-empty-sub { font-size: 13px; color: #6b7094; margin: 0; }
.kgc-empty-actions { display: flex; gap: 10px; margin-top: 8px; }
.kgc-btn-primary { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 9px; border: none; background: linear-gradient(135deg,#6366f1,#8b5cf6); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; box-shadow: 0 3px 16px rgba(99,102,241,.35); transition: all .2s; }
.kgc-btn-primary:hover { transform: translateY(-1px); box-shadow: 0 5px 20px rgba(99,102,241,.5); }
.kgc-btn-secondary { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 9px; border: 1.5px solid #3d4167; background: #232541; color: #8b8fa3; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .2s; }
.kgc-btn-secondary:hover { border-color: #6366f1; color: #a78bfa; }
.kgc-btn-lg { padding: 10px 20px; font-size: 14px; border-radius: 11px; }

/* 加载 */
.kgc-loading { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; background: #1a1b2e; }
.kgc-spin { display: flex; gap: 8px; }
.kgc-spin div { width: 10px; height: 10px; border-radius: 50%; background: #6366f1; animation: kgc-bounce 1.2s infinite ease-in-out; }
.kgc-spin div:nth-child(2) { animation-delay: .2s; }
.kgc-spin div:nth-child(3) { animation-delay: .4s; }
@keyframes kgc-bounce { 0%,80%,100%{transform:scale(0)} 40%{transform:scale(1)} }
.kgc-loading-t { font-size: 14px; font-weight: 600; color: #c4c9e2; margin: 0; }
.kgc-loading-s { font-size: 12px; color: #6b7094; margin: 0; }
</style>
