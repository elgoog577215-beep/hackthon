/**
 * 智能课程生成系统 - 共享提示词配置
 * 
 * 此文件用于前后端共享提示词系统的配置和类型定义
 * 确保前后端使用一致的参数、版本和验证规则
 * 
 * @version 1.0.0
 */

// =============================================================================
// 类型定义
// =============================================================================

/** 难度等级 */
export type DifficultyLevel = 'beginner' | 'intermediate' | 'advanced';

/** 教学风格 */
export type TeachingStyle = 'academic' | 'industrial' | 'socratic' | 'humorous';

/** 节点层级 */
export type NodeLevel = 1 | 2 | 3;

/** 节点类型 */
export type NodeType = 'original' | 'expanded' | 'redefined';

/** 提示词模板名称 */
export type PromptTemplateName = 
  | 'generate_course'
  | 'generate_sub_nodes'
  | 'generate_content'
  | 'redefine_content'
  | 'generate_quiz';

// =============================================================================
// 常量定义
// =============================================================================

/** 难度等级常量 */
export const DIFFICULTY_LEVELS = {
  BEGINNER: 'beginner' as const,
  INTERMEDIATE: 'intermediate' as const,
  ADVANCED: 'advanced' as const
};

/** 教学风格常量 */
export const TEACHING_STYLES = {
  ACADEMIC: 'academic' as const,
  INDUSTRIAL: 'industrial' as const,
  SOCRATIC: 'socratic' as const,
  HUMOROUS: 'humorous' as const
};

/** 提示词版本号 */
export const PROMPT_VERSIONS: Record<PromptTemplateName, string> = {
  generate_course: '4.0.0',
  generate_sub_nodes: '4.0.0',
  generate_content: '3.0.0',
  redefine_content: '3.0.0',
  generate_quiz: '3.0.0'
};

/** 节点层级常量 */
export const NODE_LEVELS = {
  CHAPTER: 1 as const,      // L1: 章节
  SECTION: 2 as const,      // L2: 小节
  SUBSECTION: 3 as const    // L3: 子节（内容）
};

/** 节点类型常量 */
export const NODE_TYPES = {
  ORIGINAL: 'original' as const,    // 原始生成
  EXPANDED: 'expanded' as const,    // 扩展生成
  REDEFINED: 'redefined' as const   // 重定义
};

// =============================================================================
// 参数规则
// =============================================================================

/** 参数范围规则 */
export const PARAMETER_RULES = {
  /** 章节数量 */
  chapterCount: { min: 7, max: 10 },
  
  /** 每章子章节数量 */
  subChapterCount: { 
    beginner: { min: 4, max: 6 },
    intermediate: { min: 5, max: 7 },
    advanced: { min: 5, max: 10 }
  },
  
  /** 测验题目数量 */
  questionCount: { min: 5, max: 20 },
  
  /** 内容长度限制 */
  contentLength: {
    min: 100,      // 最少字符数
    max: 10000     // 最多字符数
  },
  
  /** 公式密度 (百分比) */
  formulaDensity: {
    beginner: { min: 0, max: 10 },
    intermediate: { min: 10, max: 30 },
    advanced: { min: 30, max: 100 }
  }
};

/** 有效的难度等级列表 */
export const VALID_DIFFICULTY_LEVELS: DifficultyLevel[] = [
  'beginner',
  'intermediate',
  'advanced'
];

/** 有效的教学风格列表 */
export const VALID_TEACHING_STYLES: TeachingStyle[] = [
  'academic',
  'industrial',
  'socratic',
  'humorous'
];

/** 有效的节点类型列表 */
export const VALID_NODE_TYPES: NodeType[] = [
  'original',
  'expanded',
  'redefined'
];

// =============================================================================
// 提示词模板参数定义
// =============================================================================

/** 生成课程大纲参数 */
export interface GenerateCourseParams {
  keyword: string;
  difficulty: DifficultyLevel;
  style: TeachingStyle;
  requirements?: string;
}

/** 生成子章节参数 */
export interface GenerateSubNodesParams {
  course_name: string;
  parent_context: string;
  course_outline: string;
  difficulty: DifficultyLevel;
  style: TeachingStyle;
}

/** 生成内容参数 */
export interface GenerateContentParams {
  node_name: string;
  node_level: NodeLevel;
  course_context: string;
  difficulty: DifficultyLevel;
  style: TeachingStyle;
}

/** 重定义内容参数 */
export interface RedefineContentParams {
  node_name: string;
  original_content: string;
  user_requirement: string;
  difficulty: DifficultyLevel;
  style: TeachingStyle;
}

/** 生成测验参数 */
export interface GenerateQuizParams {
  difficulty: DifficultyLevel;
  style: TeachingStyle;
  question_count: number;
}

/** 提示词参数映射 */
export type PromptParamsMap = {
  generate_course: GenerateCourseParams;
  generate_sub_nodes: GenerateSubNodesParams;
  generate_content: GenerateContentParams;
  redefine_content: RedefineContentParams;
  generate_quiz: GenerateQuizParams;
};

// =============================================================================
// 验证函数
// =============================================================================

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

/**
 * 验证难度等级
 */
export function validateDifficulty(difficulty: string): boolean {
  return VALID_DIFFICULTY_LEVELS.includes(difficulty as DifficultyLevel);
}

/**
 * 验证教学风格
 */
export function validateStyle(style: string): boolean {
  return VALID_TEACHING_STYLES.includes(style as TeachingStyle);
}

/**
 * 验证节点类型
 */
export function validateNodeType(nodeType: string): boolean {
  return VALID_NODE_TYPES.includes(nodeType as NodeType);
}

/**
 * 验证章节数量
 */
export function validateChapterCount(count: number): boolean {
  return count >= PARAMETER_RULES.chapterCount.min && 
         count <= PARAMETER_RULES.chapterCount.max;
}

/**
 * 验证子章节数量
 */
export function validateSubChapterCount(
  count: number, 
  difficulty: DifficultyLevel
): boolean {
  const rules = PARAMETER_RULES.subChapterCount[difficulty];
  return count >= rules.min && count <= rules.max;
}

/**
 * 验证测验题目数量
 */
export function validateQuestionCount(count: number): boolean {
  return count >= PARAMETER_RULES.questionCount.min && 
         count <= PARAMETER_RULES.questionCount.max;
}

/**
 * 验证生成课程参数
 */
export function validateGenerateCourseParams(
  params: Partial<GenerateCourseParams>
): ValidationResult {
  const errors: string[] = [];
  
  if (!params.keyword || params.keyword.trim().length === 0) {
    errors.push('keyword is required and cannot be empty');
  }
  
  if (!params.difficulty) {
    errors.push('difficulty is required');
  } else if (!validateDifficulty(params.difficulty)) {
    errors.push(`Invalid difficulty: ${params.difficulty}. Must be one of: ${VALID_DIFFICULTY_LEVELS.join(', ')}`);
  }
  
  if (!params.style) {
    errors.push('style is required');
  } else if (!validateStyle(params.style)) {
    errors.push(`Invalid style: ${params.style}. Must be one of: ${VALID_TEACHING_STYLES.join(', ')}`);
  }
  
  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * 验证生成子章节参数
 */
export function validateGenerateSubNodesParams(
  params: Partial<GenerateSubNodesParams>
): ValidationResult {
  const errors: string[] = [];
  
  if (!params.course_name || params.course_name.trim().length === 0) {
    errors.push('course_name is required');
  }
  
  if (!params.parent_context || params.parent_context.trim().length === 0) {
    errors.push('parent_context is required');
  }
  
  if (!params.course_outline || params.course_outline.trim().length === 0) {
    errors.push('course_outline is required');
  }
  
  if (!params.difficulty || !validateDifficulty(params.difficulty)) {
    errors.push(`Invalid difficulty: ${params.difficulty}`);
  }
  
  if (!params.style || !validateStyle(params.style)) {
    errors.push(`Invalid style: ${params.style}`);
  }
  
  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * 验证生成内容参数
 */
export function validateGenerateContentParams(
  params: Partial<GenerateContentParams>
): ValidationResult {
  const errors: string[] = [];
  
  if (!params.node_name || params.node_name.trim().length === 0) {
    errors.push('node_name is required');
  }
  
  if (!params.node_level || ![1, 2, 3].includes(params.node_level)) {
    errors.push('node_level must be 1, 2, or 3');
  }
  
  if (!params.course_context || params.course_context.trim().length === 0) {
    errors.push('course_context is required');
  }
  
  if (!params.difficulty || !validateDifficulty(params.difficulty)) {
    errors.push(`Invalid difficulty: ${params.difficulty}`);
  }
  
  if (!params.style || !validateStyle(params.style)) {
    errors.push(`Invalid style: ${params.style}`);
  }
  
  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * 验证重定义内容参数
 */
export function validateRedefineContentParams(
  params: Partial<RedefineContentParams>
): ValidationResult {
  const errors: string[] = [];
  
  if (!params.node_name || params.node_name.trim().length === 0) {
    errors.push('node_name is required');
  }
  
  if (!params.original_content || params.original_content.trim().length === 0) {
    errors.push('original_content is required');
  }
  
  if (!params.user_requirement || params.user_requirement.trim().length === 0) {
    errors.push('user_requirement is required');
  }
  
  if (!params.difficulty || !validateDifficulty(params.difficulty)) {
    errors.push(`Invalid difficulty: ${params.difficulty}`);
  }
  
  if (!params.style || !validateStyle(params.style)) {
    errors.push(`Invalid style: ${params.style}`);
  }
  
  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * 验证生成测验参数
 */
export function validateGenerateQuizParams(
  params: Partial<GenerateQuizParams>
): ValidationResult {
  const errors: string[] = [];
  
  if (!params.difficulty || !validateDifficulty(params.difficulty)) {
    errors.push(`Invalid difficulty: ${params.difficulty}`);
  }
  
  if (!params.style || !validateStyle(params.style)) {
    errors.push(`Invalid style: ${params.style}`);
  }
  
  if (params.question_count === undefined || params.question_count === null) {
    errors.push('question_count is required');
  } else if (!validateQuestionCount(params.question_count)) {
    errors.push(`Invalid question_count: ${params.question_count}. Must be between ${PARAMETER_RULES.questionCount.min} and ${PARAMETER_RULES.questionCount.max}`);
  }
  
  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * 通用参数验证函数
 */
export function validatePromptParams<T extends PromptTemplateName>(
  templateName: T,
  params: Partial<PromptParamsMap[T]>
): ValidationResult {
  switch (templateName) {
    case 'generate_course':
      return validateGenerateCourseParams(params as Partial<GenerateCourseParams>);
    case 'generate_sub_nodes':
      return validateGenerateSubNodesParams(params as Partial<GenerateSubNodesParams>);
    case 'generate_content':
      return validateGenerateContentParams(params as Partial<GenerateContentParams>);
    case 'redefine_content':
      return validateRedefineContentParams(params as Partial<RedefineContentParams>);
    case 'generate_quiz':
      return validateGenerateQuizParams(params as Partial<GenerateQuizParams>);
    default:
      return {
        valid: false,
        errors: [`Unknown template name: ${templateName}`]
      };
  }
}

// =============================================================================
// 智能建议配置
// =============================================================================

/** 建议项类型 */
export interface SuggestionItem {
  text: string;
  type: string;
}

/** 上下文建议模式 */
export interface ContextSuggestionPattern {
  keywords: string[];
  template: string;
  type: string;
}

/** 通用智能建议 */
export const SMART_SUGGESTIONS = {
  general: [
    { text: '请帮我总结一下本章的核心概念', type: 'summary' },
    { text: '这个概念在实际项目中如何应用？', type: 'application' },
    { text: '能否用更通俗的方式解释一下？', type: 'explanation' },
    { text: '给我一些相关的练习题', type: 'practice' },
    { text: '这部分内容与其他章节有什么联系？', type: 'connection' }
  ] as SuggestionItem[],
  context: {
    maxSuggestions: 3,
    patterns: [
      {
        keywords: ['算法', 'algorithm', '复杂度', 'complexity'],
        template: '请详细讲解{nodeName}的时间复杂度分析',
        type: 'technical'
      },
      {
        keywords: ['公式', 'formula', '推导', 'proof'],
        template: '能否给出{nodeName}的完整推导过程？',
        type: 'technical'
      },
      {
        keywords: ['代码', 'code', '实现', 'implementation'],
        template: '请展示{nodeName}的代码实现示例',
        type: 'practical'
      },
      {
        keywords: ['架构', 'architecture', '设计', 'design'],
        template: '{nodeName}的架构设计有哪些关键点？',
        type: 'conceptual'
      },
      {
        keywords: ['优化', 'optimization', '性能', 'performance'],
        template: '如何优化{nodeName}的性能？',
        type: 'practical'
      }
    ] as ContextSuggestionPattern[]
  }
};

/** 上下文建议模式（便捷导出） */
export const CONTEXT_SUGGESTION_PATTERNS = SMART_SUGGESTIONS.context.patterns;

/** 基于内容类型的建议模板 */
export const CONTEXT_SUGGESTION_TEMPLATES = {
  definition: (concept: string) => `"${concept}"的核心定义是什么？`,
  formula: () => '这个公式的适用条件是什么？',
  process: () => '能梳理一下操作步骤吗？',
  example: () => '还有类似的例子吗？',
  keypoints: (concept: string) => `关于"${concept}"的重点有哪些？`,
  comparison: (concept: string) => `"${concept}"与其他相关概念有什么区别？`,
  application: () => '这个知识在实际中如何应用？',
  principle: () => '背后的原理是什么？'
};

/** 内容类型检测关键词 */
export const CONTENT_TYPE_KEYWORDS = {
  definition: ['定义', '概念', '什么是', '指'],
  formula: ['公式', '计算', '方程', '定理', '定律'],
  process: ['步骤', '流程', '过程', '方法', '算法'],
  example: ['例子', '案例', '示例', '比如', '例如'],
  comparison: ['区别', '对比', '比较', 'vs', 'versus'],
  application: ['应用', '使用', '实践', '实现', '运用'],
  principle: ['原理', '机制', '为什么', '原因']
};

/**
 * 检测内容类型
 */
export function detectContentTypes(content: string): string[] {
  const types: string[] = [];
  const lowerContent = content.toLowerCase();
  
  for (const [type, keywords] of Object.entries(CONTENT_TYPE_KEYWORDS)) {
    if (keywords.some(keyword => lowerContent.includes(keyword))) {
      types.push(type);
    }
  }
  
  return types;
}

/**
 * 生成上下文建议
 */
export function generateContextSuggestions(
  nodeName: string,
  content: string
): Array<{ text: string; type: string }> {
  const suggestions: Array<{ text: string; type: string }> = [];
  const contentTypes = detectContentTypes(content);
  
  for (const type of contentTypes.slice(0, 3)) {
    const template = CONTEXT_SUGGESTION_TEMPLATES[type as keyof typeof CONTEXT_SUGGESTION_TEMPLATES];
    if (template) {
      suggestions.push({
        text: template(nodeName),
        type
      });
    }
  }
  
  // 始终添加一个通用建议
  suggestions.push({
    text: CONTEXT_SUGGESTION_TEMPLATES.keypoints(nodeName),
    type: 'keypoints'
  });
  
  return suggestions.slice(0, 3);
}

// =============================================================================
// 导出默认配置
// =============================================================================

export default {
  DIFFICULTY_LEVELS,
  TEACHING_STYLES,
  PROMPT_VERSIONS,
  NODE_LEVELS,
  NODE_TYPES,
  PARAMETER_RULES,
  VALID_DIFFICULTY_LEVELS,
  VALID_TEACHING_STYLES,
  VALID_NODE_TYPES,
  SMART_SUGGESTIONS,
  CONTEXT_SUGGESTION_TEMPLATES,
  CONTENT_TYPE_KEYWORDS
};
