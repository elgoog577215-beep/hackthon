/**
 * 课程模板数据
 * 提供常用课程结构的快速创建
 */

export interface CourseTemplate {
  id: string
  name: string
  description: string
  icon: string
  category: string
  difficulty: 'beginner' | 'intermediate' | 'advanced'
  estimatedHours: number
  chapters: TemplateChapter[]
}

export interface TemplateChapter {
  name: string
  description?: string
  subChapters?: TemplateSubChapter[]
}

export interface TemplateSubChapter {
  name: string
  description?: string
}

export const courseTemplates: CourseTemplate[] = [
  {
    id: 'python-basics',
    name: 'Python 编程入门',
    description: '从零开始学习 Python 编程语言，掌握基础语法、数据类型、控制流和函数等核心概念',
    icon: '🐍',
    category: 'programming',
    difficulty: 'beginner',
    estimatedHours: 20,
    chapters: [
      {
        name: 'Python 基础',
        description: 'Python 简介、安装和环境配置',
        subChapters: [
          { name: 'Python 简介与历史' },
          { name: '安装 Python 和 IDE' },
          { name: '第一个 Python 程序' }
        ]
      },
      {
        name: '数据类型与变量',
        description: '学习 Python 的基本数据类型',
        subChapters: [
          { name: '数字与字符串' },
          { name: '列表与元组' },
          { name: '字典与集合' }
        ]
      },
      {
        name: '控制流',
        description: '条件语句和循环结构',
        subChapters: [
          { name: 'if-else 条件语句' },
          { name: 'for 循环' },
          { name: 'while 循环' }
        ]
      },
      {
        name: '函数与模块',
        description: '定义和使用函数，模块导入',
        subChapters: [
          { name: '定义函数' },
          { name: '参数与返回值' },
          { name: '模块与包' }
        ]
      },
      {
        name: '文件操作',
        description: '读写文件和异常处理',
        subChapters: [
          { name: '读取文件' },
          { name: '写入文件' },
          { name: '异常处理' }
        ]
      }
    ]
  },
  {
    id: 'javascript-fundamentals',
    name: 'JavaScript 核心概念',
    description: '深入理解 JavaScript 语言核心，包括 ES6+ 新特性、异步编程和 DOM 操作',
    icon: '⚡',
    category: 'programming',
    difficulty: 'intermediate',
    estimatedHours: 30,
    chapters: [
      {
        name: 'JavaScript 基础',
        description: '变量、数据类型和运算符',
        subChapters: [
          { name: '变量声明与作用域' },
          { name: '数据类型详解' },
          { name: '运算符与表达式' }
        ]
      },
      {
        name: '函数与作用域',
        description: '函数定义、调用和闭包',
        subChapters: [
          { name: '函数声明与表达式' },
          { name: '箭头函数' },
          { name: '闭包与高阶函数' }
        ]
      },
      {
        name: '对象与面向对象',
        description: '对象、原型和类',
        subChapters: [
          { name: '对象基础' },
          { name: '原型链' },
          { name: 'ES6 类' }
        ]
      },
      {
        name: '异步编程',
        description: 'Promise、async/await 和事件循环',
        subChapters: [
          { name: '回调函数' },
          { name: 'Promise' },
          { name: 'async/await' }
        ]
      },
      {
        name: 'DOM 操作',
        description: '文档对象模型和事件处理',
        subChapters: [
          { name: '选择元素' },
          { name: '修改 DOM' },
          { name: '事件处理' }
        ]
      }
    ]
  },
  {
    id: 'react-development',
    name: 'React 前端开发',
    description: '学习 React 框架，包括组件、Hooks、状态管理和路由',
    icon: '⚛️',
    category: 'programming',
    difficulty: 'intermediate',
    estimatedHours: 35,
    chapters: [
      {
        name: 'React 基础',
        description: 'React 概念和 JSX',
        subChapters: [
          { name: 'React 简介' },
          { name: 'JSX 语法' },
          { name: '组件化思想' }
        ]
      },
      {
        name: '组件与 Props',
        description: '创建和组合组件',
        subChapters: [
          { name: '函数组件' },
          { name: 'Props 传递' },
          { name: '组件组合' }
        ]
      },
      {
        name: 'State 与生命周期',
        description: '管理组件状态',
        subChapters: [
          { name: 'useState Hook' },
          { name: 'useEffect Hook' },
          { name: '状态提升' }
        ]
      },
      {
        name: 'Hooks 深入',
        description: '自定义 Hooks 和高级用法',
        subChapters: [
          { name: 'useContext' },
          { name: 'useReducer' },
          { name: '自定义 Hooks' }
        ]
      },
      {
        name: '路由与状态管理',
        description: 'React Router 和 Redux',
        subChapters: [
          { name: 'React Router' },
          { name: 'Redux 基础' },
          { name: 'Redux Toolkit' }
        ]
      }
    ]
  },
  {
    id: 'data-analysis',
    name: '数据分析入门',
    description: '使用 Python 进行数据分析，学习 Pandas、NumPy 和数据可视化',
    icon: '📊',
    category: 'data-science',
    difficulty: 'beginner',
    estimatedHours: 25,
    chapters: [
      {
        name: '数据分析概述',
        description: '数据分析流程和工具介绍',
        subChapters: [
          { name: '数据分析简介' },
          { name: 'Python 数据分析生态' },
          { name: '环境配置' }
        ]
      },
      {
        name: 'NumPy 基础',
        description: '数值计算基础',
        subChapters: [
          { name: '数组创建' },
          { name: '数组操作' },
          { name: '数学运算' }
        ]
      },
      {
        name: 'Pandas 数据处理',
        description: '数据读取、清洗和转换',
        subChapters: [
          { name: 'DataFrame 基础' },
          { name: '数据读取与写入' },
          { name: '数据清洗' }
        ]
      },
      {
        name: '数据可视化',
        description: '使用 Matplotlib 和 Seaborn',
        subChapters: [
          { name: 'Matplotlib 基础' },
          { name: '图表类型' },
          { name: 'Seaborn 美化' }
        ]
      },
      {
        name: '实战项目',
        description: '完整数据分析案例',
        subChapters: [
          { name: '数据探索' },
          { name: '分析建模' },
          { name: '报告生成' }
        ]
      }
    ]
  },
  {
    id: 'machine-learning',
    name: '机器学习基础',
    description: '机器学习核心算法和实践，包括监督学习、非监督学习和模型评估',
    icon: '🤖',
    category: 'data-science',
    difficulty: 'advanced',
    estimatedHours: 45,
    chapters: [
      {
        name: '机器学习概述',
        description: '机器学习基础概念',
        subChapters: [
          { name: '什么是机器学习' },
          { name: '学习类型' },
          { name: '开发流程' }
        ]
      },
      {
        name: '数据预处理',
        description: '特征工程和数据准备',
        subChapters: [
          { name: '数据清洗' },
          { name: '特征缩放' },
          { name: '特征选择' }
        ]
      },
      {
        name: '监督学习',
        description: '分类和回归算法',
        subChapters: [
          { name: '线性回归' },
          { name: '逻辑回归' },
          { name: '决策树' },
          { name: '随机森林' }
        ]
      },
      {
        name: '非监督学习',
        description: '聚类和降维',
        subChapters: [
          { name: 'K-Means 聚类' },
          { name: '层次聚类' },
          { name: 'PCA 降维' }
        ]
      },
      {
        name: '模型评估与优化',
        description: '评估指标和超参数调优',
        subChapters: [
          { name: '评估指标' },
          { name: '交叉验证' },
          { name: '超参数调优' }
        ]
      }
    ]
  },
  {
    id: 'product-management',
    name: '产品经理入门',
    description: '学习产品管理核心技能，包括需求分析、产品设计和项目管理',
    icon: '📱',
    category: 'product',
    difficulty: 'beginner',
    estimatedHours: 20,
    chapters: [
      {
        name: '产品管理概述',
        description: '产品经理角色和职责',
        subChapters: [
          { name: '什么是产品经理' },
          { name: '产品经理技能树' },
          { name: '产品开发流程' }
        ]
      },
      {
        name: '用户研究',
        description: '了解用户需求和行为',
        subChapters: [
          { name: '用户画像' },
          { name: '用户访谈' },
          { name: '问卷调查' }
        ]
      },
      {
        name: '需求分析',
        description: '收集和管理产品需求',
        subChapters: [
          { name: '需求收集' },
          { name: '需求优先级' },
          { name: 'PRD 文档' }
        ]
      },
      {
        name: '产品设计',
        description: '原型设计和用户体验',
        subChapters: [
          { name: '信息架构' },
          { name: '原型设计' },
          { name: '用户体验原则' }
        ]
      },
      {
        name: '项目管理',
        description: '敏捷开发和项目推进',
        subChapters: [
          { name: '敏捷开发' },
          { name: 'Scrum 框架' },
          { name: '项目推进' }
        ]
      }
    ]
  },
  {
    id: 'ui-design',
    name: 'UI 设计基础',
    description: '学习用户界面设计原则、设计工具和视觉设计系统',
    icon: '🎨',
    category: 'design',
    difficulty: 'beginner',
    estimatedHours: 25,
    chapters: [
      {
        name: '设计基础',
        description: '设计原则和色彩理论',
        subChapters: [
          { name: '设计原则' },
          { name: '色彩理论' },
          { name: '排版基础' }
        ]
      },
      {
        name: 'UI 组件',
        description: '常见 UI 组件设计',
        subChapters: [
          { name: '按钮与输入框' },
          { name: '导航与菜单' },
          { name: '卡片与列表' }
        ]
      },
      {
        name: '设计系统',
        description: '构建可复用的设计系统',
        subChapters: [
          { name: '设计令牌' },
          { name: '组件库' },
          { name: '设计规范' }
        ]
      },
      {
        name: '设计工具',
        description: 'Figma 和 Sketch 使用',
        subChapters: [
          { name: 'Figma 基础' },
          { name: '组件与变体' },
          { name: '原型与交互' }
        ]
      },
      {
        name: '设计实践',
        description: '完整界面设计案例',
        subChapters: [
          { name: '移动应用设计' },
          { name: '网页设计' },
          { name: '设计交付' }
        ]
      }
    ]
  },
  {
    id: 'digital-marketing',
    name: '数字营销基础',
    description: '学习数字营销策略、内容营销、社交媒体和数据分析',
    icon: '📢',
    category: 'business',
    difficulty: 'beginner',
    estimatedHours: 20,
    chapters: [
      {
        name: '数字营销概述',
        description: '数字营销渠道和策略',
        subChapters: [
          { name: '数字营销简介' },
          { name: '营销漏斗' },
          { name: '客户旅程' }
        ]
      },
      {
        name: '内容营销',
        description: '创建有价值的内容',
        subChapters: [
          { name: '内容策略' },
          { name: 'SEO 基础' },
          { name: '博客写作' }
        ]
      },
      {
        name: '社交媒体',
        description: '社交平台营销策略',
        subChapters: [
          { name: '平台选择' },
          { name: '内容规划' },
          { name: '社群运营' }
        ]
      },
      {
        name: '广告投放',
        description: '付费广告和效果追踪',
        subChapters: [
          { name: '广告平台' },
          { name: '受众定位' },
          { name: 'ROI 分析' }
        ]
      },
      {
        name: '数据分析',
        description: '营销数据追踪和优化',
        subChapters: [
          { name: '关键指标' },
          { name: 'Google Analytics' },
          { name: '报告与优化' }
        ]
      }
    ]
  }
]

// 分类配置
export const categoryConfig: Record<string, { name: string; icon: string; color: string }> = {
  programming: { name: '编程开发', icon: '💻', color: '#409EFF' },
  'data-science': { name: '数据科学', icon: '📈', color: '#67C23A' },
  product: { name: '产品管理', icon: '📱', color: '#E6A23C' },
  design: { name: '设计创意', icon: '🎨', color: '#F56C6C' },
  business: { name: '商业管理', icon: '💼', color: '#909399' }
}

// 难度配置
export const difficultyConfig: Record<string, { name: string; color: string }> = {
  beginner: { name: '入门', color: '#67C23A' },
  intermediate: { name: '进阶', color: '#E6A23C' },
  advanced: { name: '高级', color: '#F56C6C' }
}

// 获取所有分类
export function getAllCategories(): { value: string; label: string; icon: string; color: string }[] {
  return Object.entries(categoryConfig).map(([key, config]) => ({
    value: key,
    label: config.name,
    icon: config.icon,
    color: config.color
  }))
}

// 获取分类名称
export function getCategoryName(category: string): string {
  return categoryConfig[category]?.name || category
}

// 获取难度名称
export function getDifficultyName(difficulty: string): string {
  return difficultyConfig[difficulty]?.name || difficulty
}

// 计算模板节点数量
export function countTemplateNodes(template: CourseTemplate): number {
  let count = 1 // 根节点
  for (const chapter of template.chapters) {
    count++ // 章节节点
    if (chapter.subChapters) {
      count += chapter.subChapters.length
    }
  }
  return count
}

// 根据 ID 获取模板
export function getTemplateById(id: string): CourseTemplate | undefined {
  return courseTemplates.find(t => t.id === id)
}

// 根据分类获取模板
export function getTemplatesByCategory(category: string): CourseTemplate[] {
  return courseTemplates.filter(t => t.category === category)
}

// 根据难度获取模板
export function getTemplatesByDifficulty(difficulty: string): CourseTemplate[] {
  return courseTemplates.filter(t => t.difficulty === difficulty)
}
