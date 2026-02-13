# 课程生成系统架构文档

## 1. 系统概述

### 1.1 架构目标
- 支持多种课程类型（技术、学术、技能等）
- 提供灵活的内容生成策略
- 确保生成内容的准确性和连贯性
- 支持多模态内容（文本、图表、代码）

### 1.2 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                     课程生成系统                              │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  内容生成器  │  │  图表生成器  │  │  智能复习系统        │  │
│  │  Generator  │  │  Diagram    │  │  Review System      │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                     │             │
│         └────────────────┼─────────────────────┘             │
│                          │                                   │
│              ┌───────────▼───────────┐                       │
│              │    AI Service Core    │                       │
│              │    (LLM Integration)  │                       │
│              └───────────┬───────────┘                       │
│                          │                                   │
│              ┌───────────▼───────────┐                       │
│              │    Content Pipeline   │                       │
│              │    (Processing Flow)  │                       │
│              └───────────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

## 2. 数据模型

### 2.1 课程模型 (Course)

```typescript
interface Course {
  id: string;                    // 课程唯一标识
  title: string;                 // 课程标题
  description: string;           // 课程描述
  category: CourseCategory;      // 课程分类
  difficulty: DifficultyLevel;   // 难度等级
  targetAudience: string[];      // 目标受众
  estimatedHours: number;        // 预计学习时长
  
  // 内容结构
  chapters: Chapter[];           // 章节列表
  knowledgeGraph: KnowledgeNode[]; // 知识图谱
  
  // 元数据
  metadata: CourseMetadata;
  createdAt: Date;
  updatedAt: Date;
}
```

### 2.2 章节模型 (Chapter)

```typescript
interface Chapter {
  id: string;
  title: string;
  description: string;
  order: number;
  
  // 内容节点
  nodes: ContentNode[];
  
  // 学习统计
  progress: ChapterProgress;
  estimatedMinutes: number;
}
```

### 2.3 内容节点模型 (ContentNode)

```typescript
interface ContentNode {
  id: string;
  type: NodeType;                // 节点类型
  title: string;
  content: string;
  
  // 关联内容
  annotations: Annotation[];     // 学习笔记
  notes: Note[];                 // 个人笔记
  
  // 复习相关
  reviewItem?: ReviewItem;       // 复习项
  
  // 元数据
  metadata: NodeMetadata;
}

type NodeType = 
  | 'concept'      // 概念解释
  | 'example'      // 示例代码
  | 'exercise'     // 练习题
  | 'summary'      // 章节总结
  | 'diagram';     // 图表说明
```

### 2.4 知识图谱模型 (KnowledgeNode)

```typescript
interface KnowledgeNode {
  id: string;
  name: string;
  description: string;
  
  // 关联关系
  prerequisites: string[];       // 前置知识点
  related: string[];             // 相关知识点
  
  // 掌握度
  mastery: MasteryLevel;         // 掌握程度
  confidence: number;            // 置信度 (0-1)
}

type MasteryLevel = 
  | 'not_started'    // 未开始
  | 'learning'       // 学习中
  | 'practicing'     // 练习中
  | 'mastered';      // 已掌握
```

## 3. 生成流程

### 3.1 课程生成流程

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 需求分析  │ -> │ 大纲生成  │ -> │ 内容生成  │ -> │ 质量检查  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │               │               │
     ▼               ▼               ▼               ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│提取关键  │    │构建知识  │    │生成多模  │    │一致性   │
│信息      │    │图谱      │    │态内容    │    │验证     │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### 3.2 内容生成策略

#### 3.2.1 分层生成策略

```typescript
interface GenerationStrategy {
  // 第一层：大纲生成
  outlineGeneration: {
    method: 'hierarchical' | 'sequential';
    maxDepth: number;
    branchingFactor: number;
  };
  
  // 第二层：内容填充
  contentGeneration: {
    method: 'parallel' | 'sequential';
    chunkSize: number;
    overlap: number;
  };
  
  // 第三层：质量优化
  qualityOptimization: {
    consistencyCheck: boolean;
    factVerification: boolean;
    readabilityScore: number;
  };
}
```

#### 3.2.2 提示词模板系统

```typescript
interface PromptTemplate {
  id: string;
  name: string;
  description: string;
  
  // 模板内容
  systemPrompt: string;
  userPromptTemplate: string;
  
  // 变量定义
  variables: PromptVariable[];
  
  // 输出格式
  outputFormat: OutputFormat;
  
  // 模型配置
  modelConfig: ModelConfig;
}

interface PromptVariable {
  name: string;
  type: 'string' | 'number' | 'array' | 'object';
  required: boolean;
  description: string;
}
```

## 4. API 设计

### 4.1 课程生成 API

```typescript
// 生成课程大纲
POST /api/courses/outline
Request: {
  topic: string;
  category: CourseCategory;
  difficulty: DifficultyLevel;
  targetAudience: string[];
  estimatedHours: number;
}
Response: {
  outline: ChapterOutline[];
  knowledgeGraph: KnowledgeNode[];
}

// 生成章节内容
POST /api/courses/chapters/:id/content
Request: {
  chapterId: string;
  outline: ChapterOutline;
  style: ContentStyle;
}
Response: {
  nodes: ContentNode[];
  diagrams: Diagram[];
}

// 生成图表
POST /api/courses/diagrams
Request: {
  type: DiagramType;
  data: DiagramData;
  style: DiagramStyle;
}
Response: {
  mermaidCode: string;
  svg: string;
}
```

### 4.2 知识图谱 API

```typescript
// 获取知识图谱
GET /api/courses/:id/knowledge-graph
Response: {
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
  mastery: MasteryMap;
}

// 更新掌握度
PUT /api/knowledge-nodes/:id/mastery
Request: {
  mastery: MasteryLevel;
  confidence: number;
}
Response: {
  node: KnowledgeNode;
  affectedNodes: string[];  // 受影响的关联节点
}
```

### 4.3 智能复习 API

```typescript
// 获取复习计划
GET /api/review/schedule
Query: {
  date?: string;           // 指定日期，默认为今天
  limit?: number;          // 最大返回数量
}
Response: {
  items: ReviewItem[];
  stats: ReviewStats;
}

// 提交复习结果
POST /api/review/results
Request: {
  node_id: string;
  quality: number;         // 答题质量 0-5
  duration?: number;       // 复习时长（秒）
}
Response: {
  next_review: string;     // 下次复习时间
  interval: number;        // 复习间隔（天）
  ease_factor: number;     // 简易度因子
}
```

## 5. 状态管理

### 5.1 前端状态结构

```typescript
// stores/course.ts
interface CourseState {
  // 当前课程
  currentCourse: Course | null;
  currentChapter: Chapter | null;
  currentNode: ContentNode | null;
  
  // 课程列表
  courses: Course[];
  
  // 学习进度
  progress: {
    completedNodes: string[];
    currentPosition: Position;
    studyTime: StudyTimeStats;
  };
  
  // 智能复习
  reviewSystem: ReviewSystemState;
  
  // UI 状态
  ui: {
    sidebarOpen: boolean;
    activeTab: TabType;
    searchQuery: string;
  };
}

interface ReviewSystemState {
  items: ReviewItem[];
  stats: ReviewStats;
  currentSession: ReviewSession | null;
  mode: 'local' | 'api' | 'auto';
}
```

### 5.2 后端状态管理

```python
# 数据库模型
class Course(Base):
    __tablename__ = "courses"
    
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    category = Column(Enum(CourseCategory))
    difficulty = Column(Enum(DifficultyLevel))
    
    # 关系
    chapters = relationship("Chapter", back_populates="course")
    knowledge_graph = relationship("KnowledgeNode", back_populates="course")
    
    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

class ReviewItem(Base):
    __tablename__ = "review_items"
    
    node_id = Column(String, primary_key=True)
    node_name = Column(String, nullable=False)
    next_review = Column(DateTime, nullable=False)
    interval = Column(Integer, default=1)
    repetition_count = Column(Integer, default=0)
    ease_factor = Column(Float, default=2.5)
    
    # 关联
    user_id = Column(String, ForeignKey("users.id"))
```

## 6. 错误处理

### 6.1 错误类型

```typescript
enum ErrorCode {
  // 生成错误
  GENERATION_FAILED = 'GENERATION_FAILED',
  CONTENT_INCOMPLETE = 'CONTENT_INCOMPLETE',
  QUALITY_CHECK_FAILED = 'QUALITY_CHECK_FAILED',
  
  // 数据错误
  COURSE_NOT_FOUND = 'COURSE_NOT_FOUND',
  INVALID_COURSE_DATA = 'INVALID_COURSE_DATA',
  DUPLICATE_COURSE = 'DUPLICATE_COURSE',
  
  // API 错误
  API_RATE_LIMIT = 'API_RATE_LIMIT',
  API_TIMEOUT = 'API_TIMEOUT',
  API_ERROR = 'API_ERROR',
  
  // 复习系统错误
  REVIEW_ITEM_NOT_FOUND = 'REVIEW_ITEM_NOT_FOUND',
  INVALID_REVIEW_DATA = 'INVALID_REVIEW_DATA',
}

interface ApiError {
  code: ErrorCode;
  message: string;
  details?: Record<string, any>;
  retryable: boolean;
}
```

### 6.2 降级策略

```typescript
interface FallbackStrategy {
  // API 失败时降级到本地
  onApiFailure: 'local' | 'cache' | 'error';
  
  // 生成失败时重试
  retryConfig: {
    maxRetries: number;
    backoffMultiplier: number;
    maxDelay: number;
  };
  
  // 缓存策略
  cacheConfig: {
    ttl: number;
    maxSize: number;
  };
}
```

## 7. 性能优化

### 7.1 生成优化

```typescript
interface GenerationOptimization {
  // 流式生成
  streaming: boolean;
  
  // 分块生成
  chunking: {
    enabled: boolean;
    size: number;
    overlap: number;
  };
  
  // 并行生成
  parallelization: {
    maxConcurrency: number;
    batchSize: number;
  };
  
  // 缓存策略
  caching: {
    enabled: boolean;
    strategy: 'memory' | 'redis' | 'disk';
    ttl: number;
  };
}
```

### 7.2 加载优化

```typescript
interface LoadingOptimization {
  // 懒加载
  lazyLoading: {
    enabled: boolean;
    threshold: number;
  };
  
  // 预加载
  prefetching: {
    enabled: boolean;
    chapters: number;
    nodes: number;
  };
  
  // 虚拟滚动
  virtualScrolling: {
    enabled: boolean;
    overscan: number;
  };
}
```

## 8. 扩展性设计

### 8.1 插件系统

```typescript
interface PluginSystem {
  // 内容生成插件
  generators: ContentGenerator[];
  
  // 图表生成插件
  diagramGenerators: DiagramGenerator[];
  
  // 复习算法插件
  reviewAlgorithms: ReviewAlgorithm[];
  
  // 导出插件
  exporters: CourseExporter[];
}

interface ContentGenerator {
  name: string;
  supportedTypes: NodeType[];
  generate: (context: GenerationContext) => Promise<ContentNode>;
}
```

### 8.2 多模型支持

```typescript
interface ModelProvider {
  name: string;
  models: ModelConfig[];
  
  // 能力评估
  capabilities: {
    maxTokens: number;
    supportsStreaming: boolean;
    supportsFunctionCalling: boolean;
    languages: string[];
  };
  
  // 路由策略
  routing: {
    priority: number;
    fallbackTo: string[];
  };
}
```

## 9. 监控与日志

### 9.1 性能指标

```typescript
interface PerformanceMetrics {
  // 生成性能
  generation: {
    latency: Histogram;        // 生成延迟
    throughput: Counter;       // 吞吐量
    errorRate: Gauge;          // 错误率
  };
  
  // 系统性能
  system: {
    cpuUsage: Gauge;
    memoryUsage: Gauge;
    diskUsage: Gauge;
  };
  
  // 业务指标
  business: {
    activeUsers: Gauge;
    coursesGenerated: Counter;
    reviewsCompleted: Counter;
  };
}
```

### 9.2 日志规范

```typescript
interface LogEntry {
  timestamp: Date;
  level: 'debug' | 'info' | 'warn' | 'error';
  
  // 上下文
  context: {
    requestId: string;
    userId: string;
    courseId?: string;
  };
  
  // 消息
  message: string;
  metadata: Record<string, any>;
  
  // 错误信息
  error?: {
    code: string;
    stack?: string;
  };
}
```

## 10. 部署架构

### 10.1 服务架构

```
┌─────────────────────────────────────────────────────────────┐
│                         负载均衡器                            │
│                        (Nginx/ALB)                          │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
┌───────▼──────┐ ┌────▼────┐ ┌──────▼──────┐
│   Frontend   │ │ Backend │ │   Worker    │
│   (Vue.js)   │ │ (FastAPI)│ │  (Celery)   │
└──────────────┘ └────┬────┘ └─────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
┌───────▼──────┐ ┌────▼────┐ ┌──────▼──────┐
│  PostgreSQL  │ │  Redis  │ │  Object     │
│              │ │         │ │  Storage    │
└──────────────┘ └─────────┘ └─────────────┘
```

### 10.2 环境配置

```yaml
# docker-compose.yml
version: '3.8'

services:
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://backend:8000
  
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/db
      - REDIS_URL=redis://redis:6379
      - OPENAI_API_KEY=${OPENAI_API_KEY}
  
  worker:
    build: ./backend
    command: celery -A tasks worker --loglevel=info
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/db
      - REDIS_URL=redis://redis:6379
  
  postgres:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
```

---

## 附录

### A. 术语表

| 术语 | 说明 |
|------|------|
| ContentNode | 内容节点，课程中的最小学习单元 |
| KnowledgeNode | 知识节点，知识图谱中的知识点 |
| MasteryLevel | 掌握度等级，表示学习进度 |
| SM-2 | SuperMemo-2 算法，用于间隔重复 |
| Prompt Template | 提示词模板，用于指导 AI 生成内容 |

### B. 参考资料

1. [SM-2 Algorithm](https://www.supermemo.com/en/archives1990-2015/english/ol/sm2)
2. [FastAPI Documentation](https://fastapi.tiangolo.com/)
3. [Vue.js Composition API](https://vuejs.org/guide/extras/composition-api-faq.html)
4. [Mermaid.js](https://mermaid.js.org/)
