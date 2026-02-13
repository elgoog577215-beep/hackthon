const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export type DiagramType =
  | 'flowchart'
  | 'sequenceDiagram'
  | 'classDiagram'
  | 'stateDiagram'
  | 'erDiagram'
  | 'gantt'
  | 'pie'
  | 'mindmap'

export interface DiagramTypeInfo {
  id: DiagramType
  name: string
  description: string
  icon: string
  category: 'process' | 'structure' | 'data' | 'time'
}

export interface GenerateDiagramRequest {
  description: string
  diagram_type: DiagramType
  context?: string
}

export interface GenerateDiagramResponse {
  success: boolean
  diagram_code: string
  diagram_type: string
  description?: string
  error?: string
}

// 支持的图表类型列表
export const DIAGRAM_TYPES: DiagramTypeInfo[] = [
  {
    id: 'flowchart',
    name: '流程图',
    description: '展示流程、决策和步骤',
    icon: 'Share',
    category: 'process',
  },
  {
    id: 'sequenceDiagram',
    name: '时序图',
    description: '展示对象间的交互顺序',
    icon: 'Sort',
    category: 'process',
  },
  {
    id: 'classDiagram',
    name: '类图',
    description: '展示类结构和关系',
    icon: 'Box',
    category: 'structure',
  },
  {
    id: 'stateDiagram',
    name: '状态图',
    description: '展示状态转换',
    icon: 'Switch',
    category: 'process',
  },
  {
    id: 'erDiagram',
    name: 'ER图',
    description: '展示实体关系',
    icon: 'Connection',
    category: 'structure',
  },
  {
    id: 'gantt',
    name: '甘特图',
    description: '展示项目时间线',
    icon: 'Calendar',
    category: 'time',
  },
  {
    id: 'pie',
    name: '饼图',
    description: '展示数据占比',
    icon: 'PieChart',
    category: 'data',
  },
  {
    id: 'mindmap',
    name: '思维导图',
    description: '展示概念层次结构',
    icon: 'Grid',
    category: 'structure',
  },
]

export const diagramApi = {
  // 获取支持的图表类型
  async getDiagramTypes(): Promise<DiagramTypeInfo[]> {
    const response = await fetch(`${API_BASE_URL}/api/diagram/types`)
    if (!response.ok) {
      throw new Error('获取图表类型失败')
    }
    const data = await response.json()
    // 后端返回 { types: [...] } 格式
    return data.types || data
  },

  // 生成图表
  async generateDiagram(
    request: GenerateDiagramRequest
  ): Promise<GenerateDiagramResponse> {
    const response = await fetch(`${API_BASE_URL}/api/diagram/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || '生成图表失败')
    }

    return response.json()
  },

  // 快速生成图表（带重试）
  async generateDiagramWithRetry(
    request: GenerateDiagramRequest,
    maxRetries: number = 2
  ): Promise<GenerateDiagramResponse> {
    let lastError: Error | null = null

    for (let i = 0; i <= maxRetries; i++) {
      try {
        return await this.generateDiagram(request)
      } catch (error) {
        lastError = error as Error
        if (i < maxRetries) {
          // 等待后重试
          await new Promise((resolve) =>
            setTimeout(resolve, 1000 * (i + 1))
          )
        }
      }
    }

    throw lastError || new Error('生成图表失败')
  },
}
