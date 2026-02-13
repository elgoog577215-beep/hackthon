# 代码风格与命名规范

## 1. 通用规范

### 1.1 文件组织

```
project/
├── backend/                    # 后端代码
│   ├── models.py              # 数据模型
│   ├── services/              # 业务逻辑
│   ├── api/                   # API 路由
│   └── utils/                 # 工具函数
├── frontend/                   # 前端代码
│   ├── src/
│   │   ├── api/              # API 客户端
│   │   ├── components/       # Vue 组件
│   │   ├── stores/           # Pinia 状态管理
│   │   ├── composables/      # 组合式函数
│   │   ├── utils/            # 工具函数
│   │   └── types/            # TypeScript 类型
│   └── public/               # 静态资源
└── docs/                      # 文档
```

### 1.2 命名约定

| 类型 | 规范 | 示例 |
|------|------|------|
| 文件/目录 | kebab-case | `smart-review.ts`, `course-generator/` |
| 类/接口 | PascalCase | `CourseService`, `ReviewItem` |
| 函数/方法 | camelCase | `generateCourse()`, `getReviewSchedule()` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT`, `DEFAULT_EASE_FACTOR` |
| 变量 | camelCase | `courseId`, `reviewItems` |
| 私有属性 | _camelCase | `_privateMethod()`, `_internalState` |
| 类型别名 | PascalCase | `CourseCategory`, `MasteryLevel` |

### 1.3 注释规范

```typescript
/**
 * 生成课程大纲
 * 
 * @param topic - 课程主题
 * @param options - 生成选项
 * @returns 课程大纲数组
 * @throws {GenerationError} 当生成失败时抛出
 * 
 * @example
 * const outline = await generateOutline('Python编程', {
 *   difficulty: 'beginner',
 *   estimatedHours: 20
 * });
 */
async function generateOutline(
  topic: string,
  options: GenerationOptions
): Promise<ChapterOutline[]> {
  // 实现代码
}
```

## 2. TypeScript 规范

### 2.1 类型定义

```typescript
// ✅ 正确：使用接口定义对象类型
interface Course {
  id: string;
  title: string;
  description?: string;  // 可选属性
  readonly createdAt: Date;  // 只读属性
}

// ✅ 正确：使用类型别名定义联合类型
type CourseStatus = 'draft' | 'published' | 'archived';
type CourseOrNull = Course | null;

// ✅ 正确：使用枚举定义固定值
enum DifficultyLevel {
  BEGINNER = 'beginner',
  INTERMEDIATE = 'intermediate',
  ADVANCED = 'advanced'
}

// ❌ 错误：避免使用 any
data: any;

// ✅ 正确：使用 unknown 或具体类型
data: unknown;
data: Record<string, unknown>;
```

### 2.2 函数定义

```typescript
// ✅ 正确：显式返回类型
function calculateReviewInterval(
  quality: number,
  currentInterval: number,
  easeFactor: number
): number {
  // 实现
}

// ✅ 正确：使用箭头函数作为回调
const items = reviewItems.filter(item => item.isDue);

// ✅ 正确：使用 async/await
async function fetchCourseData(courseId: string): Promise<Course> {
  const response = await api.get(`/courses/${courseId}`);
  return response.data;
}

// ✅ 正确：使用解构和默认值
function createReviewItem({
  nodeId,
  nodeName,
  priority = 1
}: CreateReviewItemParams): ReviewItem {
  // 实现
}
```

### 2.3 错误处理

```typescript
// ✅ 正确：使用自定义错误类型
class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public statusCode: number
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// ✅ 正确：try-catch 处理异步错误
try {
  const result = await apiCall();
} catch (error) {
  if (error instanceof ApiError) {
    console.error(`API Error: ${error.code}`);
  } else {
    console.error('Unknown error:', error);
  }
}

// ✅ 正确：使用结果类型处理错误
type Result<T, E = Error> = 
  | { success: true; data: T }
  | { success: false; error: E };
```

## 3. Vue 3 规范

### 3.1 组件结构

```vue
<template>
  <!-- 模板代码 -->
</template>

<script setup lang="ts">
// 1. 导入
import { ref, computed, onMounted } from 'vue';
import type { PropType } from 'vue';

// 2. 类型定义
interface Props {
  courseId: string;
  editable?: boolean;
}

// 3. Props 和 Emits
const props = defineProps<Props>();
const emit = defineEmits<{
  (e: 'update', course: Course): void;
  (e: 'delete', id: string): void;
}>();

// 4. 注入
const courseStore = useCourseStore();

// 5. 状态
const loading = ref(false);
const course = ref<Course | null>(null);

// 6. 计算属性
const isValid = computed(() => course.value?.title.length > 0);

// 7. 方法
async function loadCourse() {
  loading.value = true;
  try {
    course.value = await courseStore.fetchCourse(props.courseId);
  } finally {
    loading.value = false;
  }
}

// 8. 生命周期
onMounted(() => {
  loadCourse();
});
</script>

<style scoped>
/* 样式代码 */
</style>
```

### 3.2 组合式函数

```typescript
// composables/useReview.ts
import { ref, computed, onMounted, onUnmounted } from 'vue';

export function useReview(courseId: string) {
  // 状态
  const reviewItems = ref<ReviewItem[]>([]);
  const loading = ref(false);
  const error = ref<Error | null>(null);
  
  // 计算属性
  const dueItems = computed(() => 
    reviewItems.value.filter(item => item.isDue)
  );
  
  // 方法
  async function loadReviewItems() {
    loading.value = true;
    error.value = null;
    
    try {
      reviewItems.value = await fetchReviewItems(courseId);
    } catch (err) {
      error.value = err as Error;
    } finally {
      loading.value = false;
    }
  }
  
  // 生命周期
  onMounted(loadReviewItems);
  
  // 清理函数
  onUnmounted(() => {
    // 清理资源
  });
  
  // 返回值
  return {
    reviewItems,
    dueItems,
    loading,
    error,
    loadReviewItems
  };
}
```

### 3.3 Pinia Store

```typescript
// stores/course.ts
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

export const useCourseStore = defineStore('course', () => {
  // State
  const courses = ref<Course[]>([]);
  const currentCourse = ref<Course | null>(null);
  const loading = ref(false);
  
  // Getters
  const courseCount = computed(() => courses.value.length);
  const publishedCourses = computed(() => 
    courses.value.filter(c => c.status === 'published')
  );
  
  // Actions
  async function fetchCourses() {
    loading.value = true;
    try {
      courses.value = await api.getCourses();
    } finally {
      loading.value = false;
    }
  }
  
  function setCurrentCourse(course: Course | null) {
    currentCourse.value = course;
  }
  
  // 返回
  return {
    courses,
    currentCourse,
    loading,
    courseCount,
    publishedCourses,
    fetchCourses,
    setCurrentCourse
  };
});
```

## 4. Python 规范

### 4.1 代码格式

```python
# ✅ 正确：使用 PEP 8 格式
class CourseService:
    """课程服务类"""
    
    def __init__(self, db: Database):
        self.db = db
        self._cache: Dict[str, Course] = {}
    
    async def generate_course(
        self,
        topic: str,
        difficulty: DifficultyLevel,
        estimated_hours: int
    ) -> Course:
        """
        生成课程
        
        Args:
            topic: 课程主题
            difficulty: 难度等级
            estimated_hours: 预计学习时长
            
        Returns:
            生成的课程对象
            
        Raises:
            GenerationError: 生成失败时抛出
        """
        # 实现代码
        pass
```

### 4.2 类型注解

```python
from typing import Optional, List, Dict, Union, Protocol
from datetime import datetime

# ✅ 正确：使用类型注解
class ReviewItem(BaseModel):
    node_id: str
    node_name: str
    next_review: datetime
    interval: int = 1
    ease_factor: float = Field(default=2.5, ge=1.3, le=3.0)

# ✅ 正确：使用 Optional
async def get_course(course_id: str) -> Optional[Course]:
    pass

# ✅ 正确：使用 Union
Result = Union[Success, Error]

# ✅ 正确：使用 Protocol
def process_items(items: Sequence[ReviewItem]) -> None:
    pass
```

### 4.3 异步编程

```python
import asyncio
from typing import AsyncGenerator

# ✅ 正确：使用 async/await
async def fetch_courses(user_id: str) -> List[Course]:
    async with db.session() as session:
        result = await session.execute(
            select(Course).where(Course.user_id == user_id)
        )
        return result.scalars().all()

# ✅ 正确：使用 asyncio.gather
async def fetch_multiple_courses(course_ids: List[str]) -> List[Course]:
    tasks = [fetch_course(cid) for cid in course_ids]
    return await asyncio.gather(*tasks)

# ✅ 正确：使用异步生成器
async def stream_course_content(course_id: str) -> AsyncGenerator[str, None]:
    async for chunk in ai_service.generate_stream(course_id):
        yield chunk
```

## 5. API 设计规范

### 5.1 RESTful API

```typescript
// ✅ 正确：使用 RESTful 命名
// 获取资源列表
GET    /api/courses              // 获取课程列表
GET    /api/courses/:id          // 获取单个课程
POST   /api/courses              // 创建课程
PUT    /api/courses/:id          // 更新课程
DELETE /api/courses/:id          // 删除课程

// 嵌套资源
GET    /api/courses/:id/chapters // 获取课程的章节
POST   /api/courses/:id/chapters // 为课程添加章节

// 动作
POST   /api/courses/:id/publish  // 发布课程
POST   /api/courses/:id/clone    // 克隆课程
```

### 5.2 请求/响应格式

```typescript
// ✅ 正确：统一的响应格式
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: Record<string, any>;
  };
  meta?: {
    page: number;
    pageSize: number;
    total: number;
  };
}

// ✅ 正确：使用 HTTP 状态码
// 200 - OK
// 201 - Created
// 400 - Bad Request
// 401 - Unauthorized
// 403 - Forbidden
// 404 - Not Found
// 422 - Validation Error
// 500 - Internal Server Error
```

## 6. 测试规范

### 6.1 单元测试

```typescript
// ✅ 正确：使用描述性测试名称
describe('CourseService', () => {
  describe('generateCourse', () => {
    it('should generate course with valid input', async () => {
      // 测试代码
    });
    
    it('should throw error when topic is empty', async () => {
      // 测试代码
    });
    
    it('should handle API timeout gracefully', async () => {
      // 测试代码
    });
  });
});

// ✅ 正确：使用 Arrange-Act-Assert 模式
it('should calculate review interval correctly', () => {
  // Arrange
  const quality = 4;
  const currentInterval = 3;
  const easeFactor = 2.5;
  
  // Act
  const result = calculateInterval(quality, currentInterval, easeFactor);
  
  // Assert
  expect(result).toBe(8);
});
```

### 6.2 测试覆盖率

```yaml
# 覆盖率目标
thresholds:
  statements: 80
  branches: 75
  functions: 80
  lines: 80
```

## 7. 文档规范

### 7.1 README 模板

```markdown
# 模块名称

## 功能描述

简要描述模块的功能和用途。

## 安装

\`\`\`bash
npm install module-name
\`\`\`

## 使用方法

\`\`\`typescript
import { functionName } from 'module-name';

const result = functionName(params);
\`\`\`

## API 文档

### functionName(params)

描述函数功能。

**参数：**

- `param1` (string): 参数说明
- `param2` (number): 参数说明

**返回值：**

- (Result): 返回值说明

## 示例

提供更多使用示例。

## 贡献

贡献指南。
```

## 8. Git 规范

### 8.1 提交信息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

**类型 (type)：**

- `feat`: 新功能
- `fix`: 修复
- `docs`: 文档
- `style`: 格式（不影响代码运行的变动）
- `refactor`: 重构
- `test`: 测试
- `chore`: 构建过程或辅助工具的变动

**示例：**

```
feat(review): 添加智能复习系统

- 实现 SM-2 算法
- 添加复习计划生成
- 支持本地和 API 两种模式

Closes #123
```

### 8.2 分支策略

```
main                    # 生产分支
├── develop             # 开发分支
├── feature/review-system   # 功能分支
├── feature/diagram-generator
├── bugfix/api-timeout
└── hotfix/critical-fix
```

## 9. 性能规范

### 9.1 前端性能

```typescript
// ✅ 正确：使用懒加载
const CourseEditor = defineAsyncComponent(() => 
  import('./components/CourseEditor.vue')
);

// ✅ 正确：使用虚拟列表
import { useVirtualList } from '@vueuse/core';

const { list, containerProps, wrapperProps } = useVirtualList(
  items,
  { itemHeight: 60 }
);

// ✅ 正确：防抖和节流
import { debounce, throttle } from 'lodash-es';

const search = debounce((query: string) => {
  performSearch(query);
}, 300);
```

### 9.2 后端性能

```python
# ✅ 正确：使用缓存
from functools import lru_cache

@lru_cache(maxsize=128)
def get_course_outline(course_id: str) -> Outline:
    return db.query(Outline).filter_by(course_id=course_id).first()

# ✅ 正确：数据库查询优化
# 使用 selectinload 避免 N+1 问题
from sqlalchemy.orm import selectinload

result = await session.execute(
    select(Course)
    .options(selectinload(Course.chapters))
    .where(Course.id == course_id)
)

# ✅ 正确：异步处理
async def generate_course_async(course_id: str):
    # 将耗时操作放入后台任务
    await celery.send_task('generate_course', args=[course_id])
```

## 10. 安全检查清单

### 10.1 前端安全

- [ ] 防止 XSS 攻击（使用 v-html 时确保内容已转义）
- [ ] 防止 CSRF 攻击（使用 CSRF Token）
- [ ] 敏感信息不存储在 localStorage
- [ ] 使用 HTTPS 传输数据
- [ ] 输入验证和清理

### 10.2 后端安全

- [ ] SQL 注入防护（使用 ORM 参数化查询）
- [ ] 身份验证和授权
- [ ] 速率限制
- [ ] 敏感数据加密存储
- [ ] 日志中不包含敏感信息

---

## 附录

### A. 推荐工具

| 类别 | 工具 | 用途 |
|------|------|------|
| 代码格式 | Prettier | 自动格式化代码 |
| 代码检查 | ESLint | TypeScript/Vue 代码检查 |
| Python 检查 | Ruff, Black | Python 代码格式和检查 |
| 类型检查 | TypeScript, mypy | 静态类型检查 |
| 测试 | Vitest, pytest | 单元测试 |
| Git 钩子 | husky, lint-staged | 提交前检查 |

### B. 配置文件示例

```json
// .eslintrc.json
{
  "extends": [
    "@vue/typescript/recommended",
    "plugin:vue/vue3-recommended"
  ],
  "rules": {
    "@typescript-eslint/explicit-function-return-type": "warn",
    "vue/multi-word-component-names": "off"
  }
}
```

```toml
# pyproject.toml
[tool.black]
line-length = 88
target-version = ['py311']

[tool.ruff]
line-length = 88
select = ["E", "F", "I", "N", "W"]
```
